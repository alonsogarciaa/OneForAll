import { useEffect, useState } from 'react'
import { FolderOpen } from 'lucide-react'
import { GlassSheet } from './GlassSheet'
import { useClient } from '../lib/engine'
import { camelotShift } from '../lib/camelot'
import { retempoName } from '../lib/format'
import { useJobsStore } from '../stores/jobsStore'
import { useUiStore } from '../stores/uiStore'
import './datasheet.css'
import type { AnalysisRecord } from '../lib/types'

const FORMATS = [
  { v: '', label: 'Como el original' },
  { v: 'wav16', label: 'WAV 16 bits' },
  { v: 'wav24', label: 'WAV 24 bits' },
  { v: 'flac', label: 'FLAC' },
  { v: 'mp3', label: 'MP3 320' }
]

const stemOf = (p: string) => p.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') ?? p
const comma = (n: number) => n.toFixed(1).replace('.', ',')

/** "Cambiar BPM y tono": a new copy of the file at another BPM and key (the original is not touched). */
export function RetempoSheet({ path, onClose }: { path: string; onClose(): void }) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const [rec, setRec] = useState<AnalysisRecord | null>(null)
  const [missing, setMissing] = useState(false)
  const [bpm, setBpm] = useState(0)
  const [semis, setSemis] = useState(0)
  const [format, setFormat] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const job = useJobsStore((s) => (jobId ? s.jobs[jobId] : undefined))

  useEffect(() => {
    client
      .getAnalysis(path)
      .then((r) => {
        if (!r.record.bpm) setMissing(true)
        else {
          setRec(r.record)
          setBpm(Math.round(r.record.bpm * 10) / 10)
        }
      })
      .catch(() => setMissing(true))
  }, [client, path])

  const src = rec?.bpm ?? 0
  const lo = Math.ceil(src * 0.5)
  const hi = Math.floor(src * 1.5)
  const running = job && !['done', 'failed', 'cancelled'].includes(job.status)

  const create = async () => {
    try {
      const r = await client.retempo(path, bpm, semis, format || undefined)
      setJobId(r.job.id)
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  return (
    <GlassSheet
      title="Cambiar BPM y tono"
      onClose={onClose}
      wide
      actions={
        <button className="btn btn-primary" disabled={!rec || !!running} onClick={() => void create()}>
          Crear copia
        </button>
      }
    >
      {missing && <p className="sheet-text">Analiza primero</p>}
      {rec && (
        <div className="retempo">
          <label className="retempo-row">
            <span className="ds-label">BPM destino</span>
            <input
              type="range"
              aria-label="BPM destino"
              min={lo}
              max={hi}
              step={0.1}
              value={bpm}
              onChange={(e) => setBpm(Number(e.target.value))}
            />
            <input
              className="field retempo-num tabular"
              type="number"
              aria-label="BPM destino (número)"
              min={lo}
              max={hi}
              step={0.1}
              value={bpm}
              onChange={(e) => setBpm(Math.min(hi, Math.max(lo, Number(e.target.value) || lo)))}
            />
            <span className="ds-sub tabular">{`${comma(src)} → ${comma(bpm)} BPM`}</span>
          </label>
          <div className="retempo-row">
            <span className="ds-label">Tonalidad</span>
            <div className="mixer-stepper">
              <button className="btn btn-sm" aria-label="Bajar tono" disabled={semis <= -12} onClick={() => setSemis((s) => s - 1)}>
                −
              </button>
              <span className="tabular">{semis > 0 ? `+${semis}` : semis}</span>
              <button className="btn btn-sm" aria-label="Subir tono" disabled={semis >= 12} onClick={() => setSemis((s) => s + 1)}>
                +
              </button>
            </div>
            {rec.camelot && <span className="ds-sub tabular">{`${rec.camelot} → ${camelotShift(rec.camelot, semis)}`}</span>}
          </div>
          <label className="retempo-row">
            <span className="ds-label">Formato</span>
            <select className="field" aria-label="Formato" value={format} onChange={(e) => setFormat(e.target.value)}>
              {FORMATS.map((f) => (
                <option key={f.v} value={f.v}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
          <p className="ds-sub">Se creará:</p>
          <p className="retempo-name">{retempoName(stemOf(path), src, bpm, rec.camelot, semis)}</p>
          {running && <span className="ds-sub tabular">{`Creando copia… ${Math.round(job!.pct)} %`}</span>}
          {job?.status === 'failed' && <span className="ds-sub txt-err">{job.error?.message ?? 'No se pudo crear la copia'}</span>}
          {job?.status === 'done' && job.result?.path && (
            <button className="btn btn-sm" onClick={() => window.oneforall.showInFolder(job.result!.path)}>
              <FolderOpen size={14} />
              Mostrar en carpeta
            </button>
          )}
        </div>
      )}
    </GlassSheet>
  )
}
