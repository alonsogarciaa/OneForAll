import { useEffect, useMemo, useState } from 'react'
import { Check } from 'lucide-react'
import { GlassSheet } from './GlassSheet'
import { DownloadButton } from './DownloadButton'
import { useClient } from '../lib/engine'
import { formatDuration } from '../lib/format'
import { useDiscoverStore } from '../stores/discoverStore'
import { useUiStore } from '../stores/uiStore'
import type { ConvertOptions, ImportItem, ImportList, MatchResult, SearchResult } from '../lib/types'
import './datasheet.css'

const SERVICE = { spotify: 'Spotify', apple: 'Apple Music', soundcloud: 'SoundCloud' } as const

function soundcloudTarget(i: ImportItem): SearchResult {
  return {
    kind: 'soundcloud', id: i.id ?? i.url ?? i.title, title: i.title, artist: i.artist, album: '', duration_s: i.duration_s,
    views: null, thumbnail: null, url: i.url ?? '', track_count: null, in_library: false, source: 'soundcloud'
  }
}

/** "Importar": a list read from a link, matched to YouTube (SoundCloud is downloaded as is), into a library playlist. */
export function ImportSheet({ list, onClose }: { list: ImportList; onClose(): void }) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const isSC = list.service === 'soundcloud'
  const [jobId, setJobId] = useState<string | null>(null)
  const matches = useDiscoverStore((s) => (jobId ? s.matches[jobId] : undefined))
  const [picked, setPicked] = useState<Record<number, string | ''>>({}) // '' = Ninguna
  const [options, setOptions] = useState<ConvertOptions>({ format: 'mp3', quality: '320' })
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    client
      .getSettings()
      .then((s: { default_format: ConvertOptions['format']; default_quality: string }) =>
        setOptions({ format: s.default_format, quality: s.default_format === 'mp3' ? s.default_quality : null })
      )
      .catch(() => undefined)
    if (isSC) return
    let id: string | null = null
    let closed = false
    client
      .importMatch(list.items)
      .then((r: { job: { id: string } }) => {
        id = r.job.id
        if (closed) void client.cancelJob(id).catch(() => undefined)
        else setJobId(id)
      })
      .catch((e: Error) => toast(e.message, 'error'))
    return () => {
      // closing the sheet stops the searches, so the next link does not wait behind them
      closed = true
      if (id) void client.cancelJob(id).catch(() => undefined)
    }
  }, [client, list, isSC, toast])

  const rows = useMemo(
    () =>
      list.items.map((item, i) => {
        if (isSC)
          return {
            item,
            m: item.preview_only
              ? ({ status: 'missing', best: null, alternatives: [] } as MatchResult)
              : ({ status: 'found', best: soundcloudTarget(item), alternatives: [] } as MatchResult)
          }
        return { item, m: matches?.[i] }
      }),
    [list, matches, isSC]
  )

  const choice = (i: number, m: MatchResult | undefined): SearchResult | null => {
    if (!m) return null
    const id = picked[i]
    if (id === '') return null
    if (id) return [m.best, ...m.alternatives].find((c) => c?.id === id) ?? null
    return m.best
  }
  const targets = rows.map((r, i) => choice(i, r.m)).filter((t): t is SearchResult => !!t)

  const start = async () => {
    setBusy(true)
    try {
      await client.startImport(list.name, targets, options)
      toast(`Descargando ${targets.length} canciones en «${list.name}»`, 'success')
      onClose()
    } catch (e: any) {
      toast(e.message, 'error')
      setBusy(false)
    }
  }

  return (
    <GlassSheet
      title="Importar"
      onClose={onClose}
      wide
      actions={
        <DownloadButton
          options={options}
          onOptions={setOptions}
          onDownload={() => void start()}
          busy={busy || targets.length === 0}
          label={`Descargar todas (${targets.length})`}
        />
      }
    >
      <div className="imp-head">
        <strong>{list.name}</strong>
        <span className="badge badge-muted">{SERVICE[list.service]}</span>
      </div>
      {list.truncated && <p className="ds-sub">Spotify solo muestra las primeras 100</p>}
      <ul className="imp-list">
        {rows.map(({ item, m }, i) => (
          <li key={i} className="imp-row">
            <div className="imp-orig">
              <span className="imp-title">{item.title}</span>
              <span className="ds-sub">
                {item.artist}
                {item.duration_s != null ? ` · ${formatDuration(item.duration_s)}` : ''}
              </span>
            </div>
            <div className="imp-match">
              {!m && <span className="ds-sub">Buscando…</span>}
              {m?.status === 'found' && !picked[i] && picked[i] !== '' && (
                <span className="imp-found">
                  <Check size={14} aria-hidden />
                  {m.best?.title}
                </span>
              )}
              {m?.status === 'missing' &&
                (item.preview_only ? (
                  <span className="badge badge-warn">Solo vista previa</span>
                ) : (
                  <span className="ds-sub">No encontrada</span>
                ))}
              {m && m.status !== 'missing' && (m.status === 'review' || picked[i] !== undefined) && (
                <>
                  {m.status === 'review' && <span className="badge badge-warn">Revisar</span>}
                  <select
                    className="field"
                    aria-label={`Elegir para «${item.title}»`}
                    value={picked[i] ?? m.best?.id ?? ''}
                    onChange={(e) => setPicked((p) => ({ ...p, [i]: e.target.value }))}
                  >
                    {[m.best, ...m.alternatives].filter(Boolean).map((c) => (
                      <option key={c!.id} value={c!.id}>
                        {`${c!.title} — ${c!.artist}${c!.duration_s != null ? ` (${formatDuration(c!.duration_s)})` : ''}`}
                      </option>
                    ))}
                    <option value="">Ninguna</option>
                  </select>
                </>
              )}
              {m?.status === 'found' && picked[i] === undefined && !isSC && (
                <button className="btn btn-sm btn-ghost" onClick={() => setPicked((p) => ({ ...p, [i]: m.best?.id ?? '' }))}>
                  Cambiar
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </GlassSheet>
  )
}
