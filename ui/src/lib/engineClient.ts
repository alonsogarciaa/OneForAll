import type {
  AnalysisRecord, AnalysisSidecar, Grid, GridOp, HarmonicRow, Section,
  ConvertOptions, DownloadRequest, EngineEvent, HistoryEntry, Job, PlaylistInfo, SearchKind, SearchResult, Settings, TrackRecord
} from './types'

export class EngineError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
    this.name = 'EngineError'
  }
}

type FetchLike = (url: string, init?: RequestInit) => Promise<Response>

interface ClientOptions {
  retries?: number
  retryDelayMs?: number
}

export type EngineClient = ReturnType<typeof createClient>

/** Where a retried playlist track goes back to (its playlist folder and position). */
export type DownloadDest = { dest_dir?: string | null; playlist_id?: number | null; position?: number | null }

export function createClient(
  { baseUrl, token }: { baseUrl: string; token: string },
  fetchImpl: FetchLike = (u, i) => fetch(u, i),
  { retries = 3, retryDelayMs = 400 }: ClientOptions = {}
) {
  async function send(path: string, init: RequestInit = {}): Promise<Response> {
    const headers: Record<string, string> = { 'X-Token': token }
    if (init.body) headers['Content-Type'] = 'application/json'
    for (let attempt = 0; ; attempt++) {
      try {
        return await fetchImpl(`${baseUrl}${path}`, { ...init, headers })
      } catch (e) {
        // Network-level failure (engine starting or restarting): retry a few times.
        if (attempt >= retries) throw new EngineError(0, 'offline', 'No se puede contactar con el motor')
        await new Promise((r) => setTimeout(r, retryDelayMs * (attempt + 1)))
      }
    }
  }

  async function json<T>(path: string, init?: RequestInit): Promise<T> {
    const r = await send(path, init)
    const body = await r.json().catch(() => null)
    if (!r.ok) {
      const d = body?.detail
      const code = typeof d === 'object' && d?.code ? d.code : 'internal'
      const message = typeof d === 'object' && d?.message ? d.message : 'Error inesperado'
      throw new EngineError(r.status, code, message)
    }
    return body as T
  }

  const post = (path: string, body: unknown) => ({ method: 'POST', body: JSON.stringify(body) })

  return {
    health: () => json<{ ok: boolean }>('/health'),
    info: () => json<{ logs_dir: string; data_dir: string }>('/info'),
    search: (q: string, kind: SearchKind) => json<SearchResult[]>(`/search?${new URLSearchParams({ q, kind })}`),
    getPlaylist: (id: string) => json<PlaylistInfo>(`/playlist/${encodeURIComponent(id)}`),
    async download(req: DownloadRequest, dest?: DownloadDest): Promise<{ job: Job } | { duplicate: TrackRecord }> {
      const r = await send('/jobs', post('/jobs', { type: 'download', request: req, ...(dest ?? {}) }))
      const body = await r.json().catch(() => null)
      if (r.status === 409) return { duplicate: body.duplicate }
      if (!r.ok) throw new EngineError(r.status, body?.detail?.code ?? 'internal', body?.detail?.message ?? 'Error inesperado')
      return body
    },
    downloadPlaylist: (id: string, options: ConvertOptions) => json<{ job: Job }>('/jobs', post('/jobs', { type: 'playlist', id, options })),
    convert: (paths: string[], options: ConvertOptions) => json<{ jobs: Job[] }>('/jobs', post('/jobs', { type: 'convert', paths, options })),
    cancelJob: (id: string) => json<{ cancelled: boolean }>(`/jobs/${id}`, { method: 'DELETE' }),
    listJobs: () => json<Job[]>('/jobs'),
    activeCount: () => json<{ count: number; by_type: Record<string, number> }>('/jobs/active-count'),
    library: (q = '') => json<TrackRecord[]>(`/library?${new URLSearchParams({ q })}`),
    history: () => json<HistoryEntry[]>('/history'),
    deleteHistory: (ids: number[] | 'all') =>
      json<{ deleted: number }>('/history', { method: 'DELETE', body: JSON.stringify(ids === 'all' ? { all: true } : { ids }) }),
    getSettings: () => json<Settings>('/settings'),
    putSettings: (s: Settings) => json<Settings>('/settings', { method: 'PUT', body: JSON.stringify(s) }),
    analyze: (paths: string[], opts: { force?: boolean; reset_bpm?: boolean } = {}) =>
      json<{ jobs: Job[] }>('/jobs', post('/jobs', { type: 'analysis', paths, ...opts })),
    getAnalysis: (path: string) => json<{ record: AnalysisRecord; sidecar: AnalysisSidecar }>(`/analysis?${new URLSearchParams({ path })}`),
    setManualBpm: (path: string, bpm: number) => json<AnalysisRecord>('/analysis/bpm', { method: 'PUT', body: JSON.stringify({ path, bpm }) }),
    harmonic: (params: { ref_track?: number; bpm?: number; camelot?: string; bpm_tolerance?: number }) =>
      json<HarmonicRow[]>(`/harmonic?${new URLSearchParams(Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]))}`),
    audioUrl: (path: string) => `${baseUrl}/audio?${new URLSearchParams({ path, token })}`,
    separate: (paths: string[], stems: string[], karaoke = false) =>
      json<{ jobs: Job[] }>('/jobs', post('/jobs', { type: 'stems', paths, stems, karaoke })),
    getStems: (path: string) =>
      json<{ folder: string | null; stems: { stem: string; file: string; size_bytes: number }[] }>(`/stems?${new URLSearchParams({ path })}`),
    putGrid: (path: string, op: GridOp) =>
      json<{ grid: Grid }>('/analysis/grid', { method: 'PUT', body: JSON.stringify({ path, ...op }) }),
    putSections: (path: string, sections: Section[] | null) =>
      json<{ sections: Section[] }>('/analysis/sections', {
        method: 'PUT',
        body: JSON.stringify(sections ? { path, sections } : { path, reset: true })
      }),
    retempo: (path: string, bpm: number, semis: number, format?: string) =>
      json<{ job: Job }>('/jobs', post('/jobs', { type: 'retempo', path, bpm, semis, ...(format ? { format } : {}) })),
    djExport: (target: 'rekordbox' | 'virtualdj' | 'serato', trackIds: number[] | null, out?: string) =>
      json<{ job: Job }>('/jobs', post('/jobs', { type: 'dj_export', target, track_ids: trackIds, ...(out ? { out } : {}) })),
    getMixerState: (path: string) => json<{ state: unknown }>(`/mixer/state?${new URLSearchParams({ path })}`),
    putMixerState: (path: string, state: unknown) =>
      json<{ ok: boolean }>('/mixer/state', { method: 'PUT', body: JSON.stringify({ path, state }) }),
    mixExport: (path: string, state: unknown, range: 'full' | 'loop', format?: string) =>
      json<{ job: Job }>('/jobs', post('/jobs', { type: 'mix_export', path, state, range, ...(format ? { format } : {}) })),
    zipStems: (path: string) => json<{ zip: string }>('/stems/zip', post('/stems/zip', { path })),
    stemsBackend: () => json<{ backend: 'cpu' | 'directml' }>('/stems/backend'),
    updateYtdlp: () => json<{ ok: boolean; output: string }>('/tools/ytdlp/update', { method: 'POST' }),

    connectEvents(onEvent: (e: EngineEvent) => void): () => void {
      let ws: WebSocket | null = null
      let closed = false
      let delay = 500
      const open = () => {
        if (closed) return
        ws = new WebSocket(`${baseUrl.replace(/^http/, 'ws')}/events?token=${encodeURIComponent(token)}`)
        ws.onopen = () => (delay = 500)
        ws.onmessage = (m) => {
          try {
            onEvent(JSON.parse(m.data))
          } catch {
            // ignore malformed event
          }
        }
        ws.onclose = () => {
          if (closed) return
          setTimeout(open, delay)
          delay = Math.min(delay * 2, 5000)
        }
      }
      open()
      return () => {
        closed = true
        ws?.close()
      }
    }
  }
}
