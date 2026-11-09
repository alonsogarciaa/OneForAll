import { useEffect, useState } from 'react'
import { FolderOpen } from 'lucide-react'
import { GlassSheet } from './GlassSheet'
import { useClient } from '../lib/engine'
import { useJobsStore } from '../stores/jobsStore'
import { useUiStore } from '../stores/uiStore'
import './datasheet.css'

type Quality = '720' | '1080' | 'max'
const QUALITIES: { id: Quality; label: string }[] = [
  { id: '720', label: '720p' },
  { id: '1080', label: '1080p' },
  { id: 'max', label: 'Máxima' }
]

interface Result {
  exported: { title: string; file: string }[]
  fallbacks: { title: string; reason: string }[]
  failed: { title: string; reason: string }[]
}

/** "Exportar vídeo…": MP4 with the original YouTube video, or the cover when there is none. */
export function VideoExportSheet({ trackIds, onClose }: { trackIds: number[]; onClose(): void }) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const [quality, setQuality] = useState<Quality>('1080')
  const [folder, setFolder] = useState<string | null>(null)
  const [defaultDir, setDefaultDir] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const job = useJobsStore((s) => (jobId ? s.jobs[jobId] : undefined))

  useEffect(() => {
    client
      .getSettings()
      .then((s: { music_dir?: string; videos_dir?: string | null }) =>
        setDefaultDir(s.videos_dir ?? (s.music_dir ? `${s.music_dir.replace(/[\\/]$/, '')}/Videos` : ''))
      )
      .catch(() => undefined)
  }, [client])

  const running = job && !['done', 'failed', 'cancelled'].includes(job.status)
  const result = job?.status === 'done' ? (job.result as unknown as Result) : null

  const run = async () => {
    try {
      const r = await client.videoExport(trackIds, quality, folder ?? undefined)
      setJobId(r.job.id)
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  const notes = result ? [...result.fallbacks, ...result.failed] : []

  return (
    <GlassSheet
      title="Exportar vídeo"
      onClose={onClose}
      wide
      actions={
        <button className="btn btn-primary" disabled={!!running || trackIds.length === 0} onClick={() => void run()}>
          Exportar
        </button>
      }
    >
      <div className="djx">
        <fieldset className="djx-group">
          <legend className="ds-label">Calidad</legend>
          {QUALITIES.map((q) => (
            <label key={q.id} className="djx-option">
              <input type="radio" name="vx-quality" checked={quality === q.id} onChange={() => setQuality(q.id)} aria-label={q.label} />
              <span>{q.label}</span>
            </label>
          ))}
        </fieldset>
        <div className="djx-dest">
          <span className="ds-sub">{`Se guardará en ${folder ?? (defaultDir || '…')}`}</span>
          <button className="btn btn-sm" onClick={async () => setFolder((await window.oneforall.pickFolder()) ?? folder)}>
            Elegir carpeta…
          </button>
        </div>
        <p className="ds-sub">Sin vídeo original (archivo propio o vídeo borrado) se usa la portada.</p>
        {running && <span className="ds-sub tabular">{`Exportando… ${Math.round(job!.pct)} %`}</span>}
        {job?.status === 'failed' && <p className="txt-err">{job.error?.message ?? 'No se pudo exportar'}</p>}
        {result && (
          <div className="djx-result">
            <p>{`${result.exported.length} exportados · ${result.fallbacks.length} con portada`}</p>
            {notes.length > 0 && (
              <ul>
                {notes.map((s, i) => (
                  <li key={i} className="ds-sub">{`${s.title} — ${s.reason}`}</li>
                ))}
              </ul>
            )}
            {result.exported.length > 0 && (
              <button className="btn btn-sm" onClick={() => window.oneforall.showInFolder(result.exported[0].file)}>
                <FolderOpen size={14} />
                Mostrar en carpeta
              </button>
            )}
          </div>
        )}
      </div>
    </GlassSheet>
  )
}
