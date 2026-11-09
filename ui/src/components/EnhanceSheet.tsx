import { useEffect, useRef, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import { GlassSheet } from './GlassSheet'
import { useClient } from '../lib/engine'
import { useJobsStore } from '../stores/jobsStore'
import { useUiStore } from '../stores/uiStore'
import './datasheet.css'

export interface EnhanceItem {
  path: string
  enhanced: boolean
}

type Mode = 'copy' | 'replace'
type Fmt = 'same' | 'flac'

const minutes = (s: number) => (s < 60 ? '< 1 min' : `${Math.round(s / 60)} min`)

/** Two aligned clips; switching mutes one and unmutes the other, so playback never stops. */
function AbPlayer({ original, enhanced }: { original: string; enhanced: string }) {
  const a = useRef<HTMLAudioElement>(null)
  const b = useRef<HTMLAudioElement>(null)
  const [side, setSide] = useState<'original' | 'enhanced'>('enhanced')
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    if (a.current) a.current.muted = side !== 'original'
    if (b.current) b.current.muted = side !== 'enhanced'
  }, [side])

  const toggle = () => {
    const els = [a.current, b.current].filter(Boolean) as HTMLAudioElement[]
    if (playing) els.forEach((el) => el.pause())
    else {
      if (b.current && a.current) b.current.currentTime = a.current.currentTime
      els.forEach((el) => void el.play?.()?.catch?.(() => undefined))
    }
    setPlaying(!playing)
  }

  return (
    <div className="enh-ab">
      <audio ref={a} src={original} preload="auto" loop />
      <audio ref={b} src={enhanced} preload="auto" loop />
      <button className="btn btn-sm icon-btn" aria-label={playing ? 'Pausa' : 'Reproducir'} onClick={toggle}>
        {playing ? <Pause size={14} /> : <Play size={14} />}
      </button>
      <div className="segmented" role="group" aria-label="Comparar">
        <button aria-pressed={side === 'original'} onClick={() => setSide('original')}>
          Original
        </button>
        <button aria-pressed={side === 'enhanced'} onClick={() => setSide('enhanced')}>
          Mejorado
        </button>
      </div>
    </div>
  )
}

/** "Mejorar audio": restore with Apollo as a new copy or in place of the original, chosen every time. */
export function EnhanceSheet({ items, onClose }: { items: EnhanceItem[]; onClose(): void }) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const [mode, setMode] = useState<Mode>('copy')
  const [fmt, setFmt] = useState<Fmt>('same')
  const [estimate, setEstimate] = useState<number | null>(null)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const preview = useJobsStore((s) => (previewId ? s.jobs[previewId] : undefined))
  const single = items.length === 1

  useEffect(() => {
    let alive = true
    Promise.all(items.map((i) => client.enhanceEstimate(i.path).catch(() => ({ seconds: null }))))
      .then((rs: { seconds: number | null }[]) => {
        const known = rs.map((r) => r.seconds).filter((s): s is number => s != null)
        if (alive) setEstimate(known.length ? known.reduce((x, y) => x + y, 0) : null)
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [client, items])

  const run = async () => {
    try {
      for (const i of items) await client.enhance(i.path, mode, fmt)
      toast(items.length > 1 ? `${items.length} canciones en cola para mejorar` : 'Mejora en cola')
      onClose()
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  const listen = async () => {
    try {
      const r = await client.enhancePreview(items[0].path)
      setPreviewId(r.job.id)
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  const previewRunning = preview && !['done', 'failed', 'cancelled'].includes(preview.status)
  const clips = preview?.status === 'done' ? (preview.result as { original: string; enhanced: string }) : null

  return (
    <GlassSheet
      title="Mejorar audio"
      onClose={onClose}
      wide
      actions={
        <button className="btn btn-primary" disabled={!items.length} onClick={() => void run()}>
          Mejorar
        </button>
      }
    >
      <div className="djx">
        {items.some((i) => i.enhanced) && <p className="ds-sub">Ya está mejorada; mejorarla otra vez no suele ayudar</p>}
        <fieldset className="djx-group">
          <legend className="ds-label">Guardar como</legend>
          <label className="djx-option">
            <input type="radio" name="enh-mode" checked={mode === 'copy'} onChange={() => setMode('copy')} aria-label="Copia nueva" />
            <span>Copia nueva</span>
          </label>
          <label className="djx-option">
            <input type="radio" name="enh-mode" checked={mode === 'replace'} onChange={() => setMode('replace')} aria-label="Reemplazar el original" />
            <span>
              Reemplazar el original
              {mode === 'replace' && <small>El original se guarda en Originales</small>}
            </span>
          </label>
        </fieldset>
        <fieldset className="djx-group">
          <legend className="ds-label">Formato</legend>
          <label className="djx-option">
            <input type="radio" name="enh-fmt" checked={fmt === 'same'} onChange={() => setFmt('same')} aria-label="Mismo formato" />
            <span>Mismo formato</span>
          </label>
          <label className="djx-option">
            <input type="radio" name="enh-fmt" checked={fmt === 'flac'} onChange={() => setFmt('flac')} aria-label="FLAC" />
            <span>FLAC</span>
          </label>
        </fieldset>
        {single && (
          <div className="djx-dest">
            {!previewId && (
              <button className="btn btn-sm" onClick={() => void listen()}>
                Escuchar antes
              </button>
            )}
            {previewRunning && <span className="ds-sub tabular">{`Preparando… ${Math.round(preview!.pct)} %`}</span>}
            {preview?.status === 'failed' && <span className="ds-sub txt-err">{preview.error?.message ?? 'No se pudo preparar'}</span>}
            {clips && <AbPlayer original={client.audioUrl(clips.original)} enhanced={client.audioUrl(clips.enhanced)} />}
          </div>
        )}
        {estimate != null && (
          <p className="ds-sub tabular">{`≈ ${minutes(estimate / items.length)} por canción · ${minutes(estimate)} en total`}</p>
        )}
      </div>
    </GlassSheet>
  )
}
