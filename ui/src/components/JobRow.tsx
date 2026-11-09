import { useState } from 'react'
import { AudioLines, ChevronRight, FolderOpen, RotateCcw, X } from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'
import { useClient } from '../lib/engine'
import { childrenOf, isFinal, useJobsStore } from '../stores/jobsStore'
import { useUiStore } from '../stores/uiStore'
import type { Job } from '../lib/types'

const STAGE_LABEL: Record<string, string> = {
  queued: 'En cola',
  running: 'Preparando',
  downloading: 'Descargando',
  converting: 'Convirtiendo',
  tagging: 'Etiquetando',
  finalizing: 'Finalizando',
  decoding: 'Analizando: leyendo audio',
  tempo: 'Analizando: tempo',
  key: 'Analizando: tonalidad',
  loudness: 'Analizando: volumen',
  waveform: 'Analizando: forma de onda',
  saving: 'Guardando',
  loading_model: 'Cargando modelo',
  separating: 'Separando',
  karaoke: 'Separando voces',
  encoding: 'Codificando',
  restoring: 'Mejorando',
  fetching_video: 'Bajando vídeo',
  rendering: 'Creando vídeo'
}

export function statusLabel(j: Job): string {
  if (j.status === 'done') return j.result?.skipped ? 'Ya en tu biblioteca' : 'Completado'
  if (j.status === 'failed') return 'Error'
  if (j.status === 'cancelled') return 'Cancelado'
  if (j.status === 'queued') return 'En cola'
  if (j.stage === 'separating') return `Separando ${Math.round(j.pct)} %`
  return STAGE_LABEL[j.stage] ?? 'En curso'
}

function useRetry() {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  return async (j: Job) => {
    const p = j.payload
    if (!p) return
    try {
      if (p.request) await client.download({ ...p.request, force: true }, { dest_dir: p.dest_dir, playlist_id: p.playlist_id, position: p.position })
      else if (p.paths) await client.convert(p.paths, p.options)
      else if (p.type === 'playlist') await client.downloadPlaylist(p.id, p.options)
      toast(`Reintentando «${j.title}»`, 'info')
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }
}

export function JobRow({ job, nested = false }: { job: Job; nested?: boolean }) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const meta = useJobsStore((s) => s.meta[job.id])
  const retry = useRetry()
  const running = job.status === 'running'
  const final = isFinal(job)

  const cancel = () => client.cancelJob(job.id).catch((e) => toast(e.message, 'error'))

  return (
    <div className={`job-row${nested ? ' job-nested' : ''}`} data-job={job.id} data-status={job.status}>
      <div className="job-main">
        <div className="job-title">{job.title}</div>
        <div className="job-sub">
          <span className={`job-status status-${job.status}`}>{statusLabel(job)}</span>
          {running && job.stage === 'downloading' && meta?.speed && (
            <span className="tabular">
              {meta.speed}
              {meta.eta ? ` · ${meta.eta}` : ''}
            </span>
          )}
          {job.status === 'failed' && job.error && <span className="job-error">{job.error.message}</span>}
        </div>
        {!final && (
          <div className="progress job-progress" aria-label={`Progreso ${Math.round(job.pct)}%`}>
            <div className={running ? 'is-animating' : undefined} style={{ width: `${job.pct}%` }} />
          </div>
        )}
      </div>
      <div className="job-actions">
        {!final && (
          <button className="btn btn-sm" onClick={cancel}>
            <X size={14} />
            Cancelar
          </button>
        )}
        {job.status === 'done' && job.result?.path && (
          <button className="btn btn-sm btn-ghost" onClick={() => useUiStore.getState().openData(job.result!.path)}>
            <AudioLines size={14} />
            Datos
          </button>
        )}
        {job.status === 'done' && job.result?.path && (
          <button className="btn btn-sm btn-ghost" onClick={() => window.oneforall.showInFolder(job.result!.path)}>
            <FolderOpen size={14} />
            Mostrar en carpeta
          </button>
        )}
        {job.status === 'failed' && job.payload && (
          <button className="btn btn-sm" onClick={() => retry(job)}>
            <RotateCcw size={14} />
            Reintentar
          </button>
        )}
      </div>
    </div>
  )
}

export function PlaylistJobRow({ job }: { job: Job }) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const kids = useJobsStore(useShallow((s) => childrenOf(s, job.id)))
  const [open, setOpen] = useState(!isFinal(job))
  const finished = kids.filter(isFinal).length
  const final = isFinal(job)
  return (
    <div className="job-group">
      <div className="job-row" data-job={job.id} data-status={job.status}>
        <button className="btn btn-ghost icon-btn btn-sm job-toggle" aria-expanded={open} aria-label={open ? 'Contraer' : 'Expandir'} onClick={() => setOpen((v) => !v)}>
          <ChevronRight size={16} style={{ transform: open ? 'rotate(90deg)' : undefined }} />
        </button>
        <div className="job-main">
          <div className="job-title">{job.title}</div>
          <div className="job-sub">
            <span className={`job-status status-${job.status}`}>{final ? statusLabel(job) : 'Playlist'}</span>
            <span className="tabular">
              {finished} / {kids.length || '…'}
            </span>
          </div>
          {!final && (
            <div className="progress job-progress">
              <div className={job.status === 'running' ? 'is-animating' : undefined} style={{ width: `${job.pct}%` }} />
            </div>
          )}
        </div>
        <div className="job-actions">
          {!final && (
            <button className="btn btn-sm" onClick={() => client.cancelJob(job.id).catch((e) => toast(e.message, 'error'))}>
              <X size={14} />
              Cancelar playlist
            </button>
          )}
        </div>
      </div>
      {open && kids.map((k) => <JobRow key={k.id} job={k} nested />)}
    </div>
  )
}
