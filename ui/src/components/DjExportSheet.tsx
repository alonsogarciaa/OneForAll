import { useEffect, useState } from 'react'
import { FolderOpen } from 'lucide-react'
import { GlassSheet } from './GlassSheet'
import { useClient } from '../lib/engine'
import { useJobsStore } from '../stores/jobsStore'
import { useUiStore } from '../stores/uiStore'
import './datasheet.css'

type Target = 'rekordbox' | 'virtualdj' | 'serato'

const TARGETS: { id: Target; name: string; note: string }[] = [
  { id: 'rekordbox', name: 'Rekordbox', note: 'Importa el XML en Rekordbox: Preferencias → Avanzado → rekordbox xml' },
  { id: 'virtualdj', name: 'VirtualDJ', note: 'Cierra VirtualDJ antes de exportar' },
  { id: 'serato', name: 'Serato', note: 'Se escribe en las etiquetas de cada archivo (MP3, FLAC, M4A)' }
]
const FILE = 'OneForAll rekordbox.xml'

/** "Exportar a…": BPM, key, beat grid and section cues to Rekordbox, VirtualDJ or Serato. */
export function DjExportSheet({ trackIds, onClose }: { trackIds: number[] | null; onClose(): void }) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const [target, setTarget] = useState<Target>('rekordbox')
  const [all, setAll] = useState(trackIds === null)
  const [folder, setFolder] = useState<string | null>(null)
  const [musicDir, setMusicDir] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const job = useJobsStore((s) => (jobId ? s.jobs[jobId] : undefined))

  useEffect(() => {
    client
      .getSettings()
      .then((s: { music_dir?: string }) => setMusicDir(s.music_dir ?? ''))
      .catch(() => undefined)
  }, [client])

  const base = folder ?? musicDir
  const dest = base ? `${base.replace(/[\\/]$/, '')}${base.includes('/') ? '/' : '\\'}${FILE}` : ''
  const running = job && !['done', 'failed', 'cancelled'].includes(job.status)
  const result = job?.status === 'done' ? (job.result as { exported: number; skipped: { title: string; reason: string }[]; file: string | null }) : null

  const run = async () => {
    try {
      const out = target === 'rekordbox' && folder ? `${folder.replace(/[\\/]$/, '')}/${FILE}` : undefined
      const r = await client.djExport(target, all ? null : trackIds, out)
      setJobId(r.job.id)
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  return (
    <GlassSheet
      title="Exportar a…"
      onClose={onClose}
      wide
      actions={
        <button className="btn btn-primary" disabled={!!running} onClick={() => void run()}>
          Exportar
        </button>
      }
    >
      <div className="djx">
        <fieldset className="djx-group">
          <legend className="ds-label">Programa</legend>
          {TARGETS.map((t) => (
            <label key={t.id} className="djx-option">
              <input type="radio" name="djx-target" checked={target === t.id} onChange={() => setTarget(t.id)} aria-label={t.name} />
              <span>
                <strong>{t.name}</strong>
                {target === t.id && <small>{t.note}</small>}
              </span>
            </label>
          ))}
        </fieldset>
        <fieldset className="djx-group">
          <legend className="ds-label">Pistas</legend>
          {trackIds !== null && (
            <label className="djx-option">
              <input type="radio" name="djx-scope" checked={!all} onChange={() => setAll(false)} aria-label={`Seleccionadas (${trackIds.length})`} />
              <span>{`Seleccionadas (${trackIds.length})`}</span>
            </label>
          )}
          <label className="djx-option">
            <input type="radio" name="djx-scope" checked={all} onChange={() => setAll(true)} aria-label="Toda la biblioteca" />
            <span>Toda la biblioteca</span>
          </label>
        </fieldset>
        {target === 'rekordbox' && (
          <div className="djx-dest">
            <span className="ds-sub">{dest ? `Se guardará en ${dest}` : 'Se guardará en …'}</span>
            <button className="btn btn-sm" onClick={async () => setFolder((await window.oneforall.pickFolder()) ?? folder)}>
              Elegir carpeta…
            </button>
          </div>
        )}
        {running && <span className="ds-sub tabular">{`Exportando… ${Math.round(job!.pct)} %`}</span>}
        {job?.status === 'failed' && <p className="txt-err">{job.error?.message ?? 'No se pudo exportar'}</p>}
        {result && (
          <div className="djx-result">
            <p>{`${result.exported} exportadas · ${result.skipped.length} saltadas`}</p>
            {result.skipped.length > 0 && (
              <ul>
                {result.skipped.map((s, i) => (
                  <li key={i} className="ds-sub">{`${s.title} — ${s.reason}`}</li>
                ))}
              </ul>
            )}
            {result.file && (
              <button className="btn btn-sm" onClick={() => window.oneforall.showInFolder(result.file!)}>
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
