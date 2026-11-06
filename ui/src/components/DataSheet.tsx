import { useCallback, useEffect, useRef, useState } from 'react'
import { FolderOpen, Pause, Play, RefreshCw, X } from 'lucide-react'
import { GlassSheet } from './GlassSheet'
import { Waveform } from './Waveform'
import { StemsSection } from './StemsSection'
import { GridControls } from './GridControls'
import { useClient } from '../lib/engine'
import { displayKey } from '../lib/camelot'
import { formatDuration } from '../lib/format'
import { TapTempo } from '../lib/tapTempo'
import { useJobsStore } from '../stores/jobsStore'
import { useUiStore } from '../stores/uiStore'
import type { AnalysisRecord, AnalysisSidecar } from '../lib/types'
import './datasheet.css'

interface Loaded {
  record: AnalysisRecord
  sidecar: AnalysisSidecar
  info?: { format: string; bitrate: number | null; sample_rate: number | null }
}

const STAGES: Record<string, string> = {
  queued: 'En cola', running: 'Preparando', decoding: 'Leyendo audio', tempo: 'Calculando tempo',
  key: 'Detectando tonalidad', loudness: 'Midiendo volumen', waveform: 'Dibujando onda', saving: 'Guardando'
}

const baseName = (p: string) => p.split(/[\\/]/).pop() ?? p

function infoLine(i?: Loaded['info']): string | null {
  if (!i) return null
  const parts = [i.format.toUpperCase()]
  if (i.bitrate) parts.push(`${i.bitrate} kbps`)
  if (i.sample_rate) parts.push(`${(i.sample_rate / 1000).toLocaleString('es-ES', { maximumFractionDigits: 1 })} kHz`)
  return parts.join(' · ')
}

/** The engine accepts a manual BPM strictly between these. */
const MIN_BPM = 20
const MAX_BPM = 400

export function DataSheet({ path, onClose }: { path: string; onClose(): void }) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const [data, setData] = useState<Loaded | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const job = useJobsStore((s) => (jobId ? s.jobs[jobId] : undefined))
  const audio = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)
  const [position, setPosition] = useState(0)
  const tapper = useRef(new TapTempo())
  const [tapBpm, setTapBpm] = useState<number | null>(null)
  const started = useRef(false)
  const [gridMode, setGridMode] = useState(false)

  const load = useCallback(
    async (analyzeIfMissing: boolean) => {
      try {
        setData(await client.getAnalysis(path))
        setError(null)
      } catch (e: any) {
        if (e?.status === 404 && analyzeIfMissing && !started.current) {
          started.current = true
          const r = await client.analyze([path])
          setJobId(r.jobs[0]?.id ?? null)
        } else if (e?.status !== 404 || !analyzeIfMissing) {
          setError(e?.status === 404 ? 'No se pudo obtener el análisis de este archivo' : e.message)
        }
      }
    },
    [client, path]
  )

  useEffect(() => {
    load(true)
  }, [load])

  // When the analysis job finishes, reload (or show its error).
  useEffect(() => {
    if (!job) return
    if (job.status === 'done') {
      setJobId(null)
      load(false)
    } else if (job.status === 'failed') {
      setError(job.error?.message ?? 'No se pudo analizar')
      setJobId(null)
    } else if (job.status === 'cancelled') {
      setJobId(null)
      if (!data) onClose() // nothing to show yet; a cancelled re-analysis keeps the current data on screen
    }
  }, [job, load, onClose, data])

  const tap = useCallback(() => setTapBpm(tapper.current.tap()), [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      const typing = el != null && (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(el.tagName) || el.isContentEditable)
      if (e.code === 'Space' && !typing) {
        if (e.repeat) {
          e.preventDefault() // a held key is not a tap
          return
        }
        e.preventDefault()
        tap()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [tap])

  const applyTap = async () => {
    if (tapBpm == null || !(tapBpm > MIN_BPM && tapBpm < MAX_BPM)) return
    try {
      await client.setManualBpm(path, tapBpm)
      tapper.current.reset()
      setTapBpm(null)
      await load(false)
      toast(`BPM fijado en ${tapBpm.toFixed(1)}`, 'success')
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  const tapValid = tapBpm != null && tapBpm > MIN_BPM && tapBpm < MAX_BPM

  const resetBpm = async () => {
    try {
      const r = await client.analyze([path], { reset_bpm: true })
      setJobId(r.jobs[0]?.id ?? null)
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  const reanalyze = async () => {
    try {
      const r = await client.analyze([path], { force: true })
      setJobId(r.jobs[0]?.id ?? null)
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  const togglePlay = () => {
    const a = audio.current
    if (!a) return
    if (a.paused) a.play().catch(() => toast('No se puede reproducir este archivo', 'error'))
    else a.pause()
  }

  const r = data?.record
  const analyzing = jobId !== null

  return (
    <GlassSheet
      title={baseName(path)}
      onClose={onClose}
      wide
      actions={
        <>
          <button className="btn" onClick={() => window.oneforall.showInFolder(path)}>
            <FolderOpen size={15} />
            Mostrar en carpeta
          </button>
          <button className="btn" onClick={reanalyze} disabled={analyzing}>
            <RefreshCw size={15} />
            Reanalizar
          </button>
        </>
      }
    >
      {analyzing && (
        <div className="ds-progress">
          <span>Analizando… {job ? STAGES[job.stage] ?? '' : ''}</span>
          <div className="progress"><div className="is-animating" style={{ width: `${job?.pct ?? 0}%` }} /></div>
          <button className="btn btn-sm" onClick={() => jobId && client.cancelJob(jobId)}>
            <X size={14} />
            Cancelar
          </button>
        </div>
      )}
      {error && <p className="sheet-text txt-err">{error}</p>}
      {r && data && (
        <>
          <div className="ds-wave">
            <button className="btn btn-primary icon-btn ds-play" aria-label={playing ? 'Pausa' : 'Reproducir'} onClick={togglePlay}>
              {playing ? <Pause size={16} /> : <Play size={16} />}
            </button>
            <Waveform
              data={data.sidecar.waveform}
              beats={data.sidecar.beats}
              duration={data.sidecar.duration}
              position={position}
              onSeek={(s) => {
                if (audio.current) audio.current.currentTime = s
                setPosition(s)
              }}
            />
            <span className="ds-time tabular">
              {formatDuration(position)} / {formatDuration(data.sidecar.duration)}
            </span>
            <button className="btn btn-sm" aria-pressed={gridMode} onClick={() => setGridMode((v) => !v)}>
              Rejilla
            </button>
            <audio
              ref={audio}
              src={client.audioUrl(path)}
              preload="none"
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              onTimeUpdate={(e) => setPosition(e.currentTarget.currentTime)}
            />
          </div>
          {data.sidecar.needs_reanalysis && <p className="ds-sub ds-notice">Reanaliza para detectar secciones</p>}
          {gridMode && (
            <GridControls
              path={path}
              grid={data.sidecar.grid ?? { anchor: data.sidecar.beats[0] ?? 0, bpm: r.bpm ?? 0, source: 'auto', meter: 4 }}
              position={position}
              audio={audio.current}
              onChange={() => void load(false)}
            />
          )}
          <div className="ds-grid">
            <div className="ds-fact ds-big">
              <span className="ds-label">BPM</span>
              <span className="ds-value tabular">{r.bpm != null ? r.bpm.toFixed(1) : '—'}</span>
              <span className="ds-badges">
                {r.bpm_source === 'manual' && <span className="badge badge-muted">manual</span>}
                {r.bpm_source === 'manual' && (
                  <button className="btn btn-sm" onClick={resetBpm} disabled={analyzing}>
                    Volver al automático
                  </button>
                )}
                {r.bpm_source === 'auto' && r.bpm_confidence != null && r.bpm_confidence < 0.5 && (
                  <span className="badge badge-warn">confianza baja</span>
                )}
              </span>
            </div>
            <div className="ds-fact ds-big">
              <span className="ds-label">Tonalidad</span>
              <span className="ds-value">{displayKey(r.camelot)}</span>
            </div>
            <div className="ds-fact">
              <span className="ds-label">Volumen</span>
              <span className="tabular">{r.lufs != null ? `${r.lufs.toFixed(1)} LUFS` : '—'}</span>
              <span className="ds-sub tabular">pico {r.peak_db != null ? `${r.peak_db.toFixed(1)} dBFS` : '—'}</span>
            </div>
            <div className="ds-fact">
              <span className="ds-label">Duración</span>
              <span className="tabular">{formatDuration(data.sidecar.duration)}</span>
              {infoLine(data.info) && <span className="ds-sub">{infoLine(data.info)}</span>}
            </div>
            <div className="ds-tap">
              <span className="ds-label">Tap tempo</span>
              <span className="tap-bpm tabular">{tapBpm != null ? tapBpm.toFixed(1) : '—'}</span>
              <div className="ds-tap-actions">
                <button className="btn" onClick={tap}>Tap</button>
                <button className="btn btn-primary" disabled={!tapValid || analyzing} onClick={applyTap}>Aplicar</button>
              </div>
              <span className="ds-sub">Pulsa Tap o la barra espaciadora al ritmo</span>
            </div>
          </div>
        </>
      )}
      <StemsSection path={path} durationS={data?.sidecar.duration ?? null} />
    </GlassSheet>
  )
}
