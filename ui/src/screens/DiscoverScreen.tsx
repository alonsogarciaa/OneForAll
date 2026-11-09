import { useEffect, useMemo, useRef, useState } from 'react'
import { Compass } from 'lucide-react'
import { ResultRow } from '../components/ResultRow'
import { useClient } from '../lib/engine'
import { fit, type Fit } from '../lib/fit'
import { useDiscoverStore, type QuickInfo } from '../stores/discoverStore'
import { useUiStore } from '../stores/uiStore'
import type { ConvertOptions, MoodSection, Rec, SearchResult, TrackRecord } from '../lib/types'
import './search.css'
import './discover.css'

type Tab = 'similar' | 'moods'
type Order = 'youtube' | 'fit'
const FIT_RANK: Record<string, number> = { encaja: 0, cerca: 1, none: 2, pending: 3 }

const comma = (n: number) => n.toFixed(1).replace('.', ',')

function asRec(r: SearchResult): Rec {
  return { ...r, bpm: null, camelot: null, analysed: false }
}

/** Rows with what we know so far; starts the quick analysis for the unknown ones and cancels it on leave. */
function useQuick(rows: Rec[]) {
  const client = useClient()
  const quick = useDiscoverStore((s) => s.quick)
  const setQuick = useDiscoverStore((s) => s.setQuick)

  useEffect(() => {
    const known: Record<string, QuickInfo> = {}
    for (const r of rows) if (r.analysed) known[r.id] = { bpm: r.bpm, camelot: r.camelot, failed: r.bpm == null }
    if (Object.keys(known).length) setQuick(known)
    const todo = rows.filter((r) => !r.analysed && !useDiscoverStore.getState().quick[r.id] && r.source !== 'soundcloud')
    if (!todo.length) return
    let jobId: string | null = null
    let left = false
    client
      .quickAnalysis(todo.map((r) => r.id), todo.map((r) => r.duration_s))
      .then((r: { job: { id: string } }) => {
        jobId = r.job.id
        if (left) void client.cancelJob(jobId).catch(() => undefined)
      })
      .catch(() => undefined)
    return () => {
      left = true
      if (jobId) void client.cancelJob(jobId).catch(() => undefined)
    }
  }, [client, rows, setQuick])

  return quick
}

function RecList({ rows, refBpm, refCamelot, options, onOptions }: {
  rows: Rec[]
  refBpm: number | null
  refCamelot: string | null
  options: ConvertOptions
  onOptions(o: ConvertOptions): void
}) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const quick = useQuick(rows)
  const [order, setOrder] = useState<Order>('youtube')

  const view = useMemo(() => {
    const items = rows.map((r) => {
      const q = quick[r.id]
      const f: Fit = q && !q.failed ? fit(refBpm, refCamelot, q.bpm, q.camelot) : null
      return { r, q, rank: !q ? 'pending' : (f ?? 'none') }
    })
    if (order === 'fit') return [...items].sort((a, b) => FIT_RANK[a.rank] - FIT_RANK[b.rank])
    return items
  }, [rows, quick, refBpm, refCamelot, order])

  const download = async (item: SearchResult) => {
    try {
      const r = await client.download({ target: item, options, force: false })
      toast('duplicate' in r ? `«${item.title}» ya está en tu biblioteca` : `Descargando «${item.title}»`, 'success')
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  return (
    <>
      <div className="segmented disc-order" role="group" aria-label="Orden">
        <button aria-pressed={order === 'youtube'} onClick={() => setOrder('youtube')}>
          Orden de YouTube
        </button>
        <button aria-pressed={order === 'fit'} onClick={() => setOrder('fit')}>
          Mejor encaje
        </button>
      </div>
      <div className="results disc-results">
        {view.map(({ r, q, rank }) => (
          <ResultRow
            key={r.id}
            item={r}
            options={options}
            onOptions={onOptions}
            onDownload={(i) => void download(i)}
            onOpen={() => undefined}
            extra={
              <div className="disc-facts tabular">
                {!q ? (
                  <span className="ds-sub">analizando…</span>
                ) : (
                  <>
                    <span>{q.bpm != null ? comma(q.bpm) : '—'}</span>
                    <span>{q.camelot ?? '—'}</span>
                  </>
                )}
                {rank === 'encaja' && <span className="badge badge-fit">Encaja</span>}
                {rank === 'cerca' && <span className="badge badge-muted">Cerca</span>}
              </div>
            }
          />
        ))}
      </div>
    </>
  )
}

function Similar({ options, onOptions }: { options: ConvertOptions; onOptions(o: ConvertOptions): void }) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const seedId = useUiStore((s) => s.discoverSeed)
  const [tracks, setTracks] = useState<TrackRecord[]>([])
  const [rows, setRows] = useState<Rec[] | null>(null)

  useEffect(() => {
    client.library().then(setTracks).catch(() => undefined)
  }, [client])

  useEffect(() => {
    if (seedId == null) return
    setRows(null)
    client
      .similar({ trackId: seedId })
      .then((r: { items: Rec[] }) => setRows(r.items))
      .catch((e: Error) => (toast(e.message, 'error'), setRows([])))
  }, [client, seedId, toast])

  const seed = tracks.find((t) => t.id === seedId) ?? null
  return (
    <>
      <label className="disc-seed">
        <span className="ds-label">Parecidas a</span>
        <select
          className="field"
          aria-label="Canción de referencia"
          value={seedId ?? ''}
          onChange={(e) => useUiStore.getState().openDiscover(Number(e.target.value))}
        >
          <option value="" disabled>
            Elige una canción de tu biblioteca
          </option>
          {tracks.map((t) => (
            <option key={t.id} value={t.id}>{`${t.artist} – ${t.title}`}</option>
          ))}
        </select>
        {seed?.bpm != null && <span className="ds-sub tabular">{`${comma(seed.bpm)} BPM · ${seed.camelot ?? '—'}`}</span>}
      </label>
      {rows && rows.length === 0 && <p className="empty-inline">No se encontraron recomendaciones</p>}
      {rows && rows.length > 0 && (
        <RecList rows={rows} refBpm={seed?.bpm ?? null} refCamelot={seed?.camelot ?? null} options={options} onOptions={onOptions} />
      )}
      {seedId != null && !rows && <div className="results-loading" aria-label="Cargando" />}
    </>
  )
}

function Moods({ options, onOptions }: { options: ConvertOptions; onOptions(o: ConvertOptions): void }) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const [sections, setSections] = useState<MoodSection[] | null>(null)
  const [playlists, setPlaylists] = useState<SearchResult[] | null>(null)
  const [rows, setRows] = useState<Rec[] | null>(null)
  const [bpm, setBpm] = useState('')
  const [key, setKey] = useState('')

  useEffect(() => {
    client.moods().then(setSections).catch((e: Error) => (toast(e.message, 'error'), setSections([])))
  }, [client, toast])

  const openMood = async (params: string) => {
    setRows(null)
    try {
      setPlaylists(await client.moodPlaylists(params))
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }
  const openPlaylist = async (id: string) => {
    try {
      const pl = await client.getPlaylist(id)
      setRows(pl.tracks.map(asRec))
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  const refBpm = Number(bpm.replace(',', '.')) || null
  const refKey = /^(1[0-2]|[1-9])[AB]$/i.test(key.trim()) ? key.trim().toUpperCase() : null

  return (
    <>
      <div className="disc-ref">
        <input className="field disc-bpm" inputMode="decimal" aria-label="BPM de referencia" placeholder="BPM"
               value={bpm} onChange={(e) => setBpm(e.target.value)} />
        <input className="field disc-key" aria-label="Tonalidad de referencia" placeholder="8A"
               value={key} onChange={(e) => setKey(e.target.value)} />
      </div>
      {!rows &&
        sections?.map((s) => (
          <div key={s.title} className="disc-moods">
            <h2 className="ds-label">{s.title}</h2>
            <div className="disc-chips">
              {s.items.map((i) => (
                <button key={i.params} className="btn btn-sm" onClick={() => void openMood(i.params)}>
                  {i.title}
                </button>
              ))}
            </div>
          </div>
        ))}
      {!rows && playlists && (
        <div className="disc-chips disc-playlists">
          {playlists.map((p) => (
            <button key={p.id} className="btn btn-sm" onClick={() => void openPlaylist(p.id)}>
              {p.title}
            </button>
          ))}
        </div>
      )}
      {rows && (
        <>
          <button className="btn btn-sm btn-ghost" onClick={() => setRows(null)}>
            ← Volver
          </button>
          <RecList rows={rows} refBpm={refBpm} refCamelot={refKey} options={options} onOptions={onOptions} />
        </>
      )}
    </>
  )
}

/** "Descubrir": songs like one of yours, or by mood and genre, with BPM and key worked out on the fly. */
export function DiscoverScreen() {
  const client = useClient()
  const [tab, setTab] = useState<Tab>('similar')
  const [options, setOptions] = useState<ConvertOptions>({ format: 'mp3', quality: '320' })
  const loaded = useRef(false)

  useEffect(() => {
    if (loaded.current) return
    loaded.current = true
    client
      .getSettings()
      .then((s: { default_format: ConvertOptions['format']; default_quality: string }) =>
        setOptions({ format: s.default_format, quality: s.default_format === 'mp3' ? s.default_quality : null })
      )
      .catch(() => undefined)
  }, [client])

  return (
    <section className="search-screen discover">
      <div className="screen-head">
        <h1 className="screen-title">Descubrir</h1>
        <div className="segmented" role="group" aria-label="Tipo de recomendación">
          <button aria-pressed={tab === 'similar'} onClick={() => setTab('similar')}>
            Parecidas a…
          </button>
          <button aria-pressed={tab === 'moods'} onClick={() => setTab('moods')}>
            Moods y géneros
          </button>
        </div>
      </div>
      {tab === 'similar' ? <Similar options={options} onOptions={setOptions} /> : <Moods options={options} onOptions={setOptions} />}
      {tab === 'similar' && useUiStore.getState().discoverSeed == null && (
        <div className="empty">
          <Compass size={40} strokeWidth={1.4} />
          <p>Elige una canción de tu biblioteca para ver otras que encajen con ella</p>
        </div>
      )}
    </section>
  )
}
