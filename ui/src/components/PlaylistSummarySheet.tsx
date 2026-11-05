import { useEffect, useRef, useState } from 'react'
import { GlassSheet } from './GlassSheet'
import { useClient } from '../lib/engine'
import { useJobsStore } from '../stores/jobsStore'
import { useUiStore } from '../stores/uiStore'
import type { Job } from '../lib/types'

export function PlaylistSummarySheet({ job, onClose }: { job: Job; onClose(): void }) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const r = job.result ?? {}
  const failed: { title: string; message: string; target: any; dest_dir?: string; playlist_id?: number; position?: number }[] = r.failed ?? []

  const retryFailed = async () => {
    onClose()
    for (const f of failed) {
      try {
        await client.download({ target: f.target, options: r.options, force: true }, { dest_dir: f.dest_dir, playlist_id: f.playlist_id, position: f.position })
      } catch (e: any) {
        toast(e.message, 'error')
      }
    }
    toast(`Reintentando ${failed.length} canciones`, 'info')
  }

  return (
    <GlassSheet
      title={`Playlist «${job.title}» terminada`}
      onClose={onClose}
      actions={
        <>
          <button className="btn" onClick={onClose}>
            Cerrar
          </button>
          {failed.length > 0 && (
            <button className="btn btn-primary" onClick={retryFailed}>
              Reintentar fallidas
            </button>
          )}
        </>
      }
    >
      <p className="summary-line tabular">
        {r.done ?? 0} descargadas · {failed.length} fallidas · {r.skipped ?? 0} ya en tu biblioteca
      </p>
      {failed.length > 0 && (
        <ul className="failed-list">
          {failed.map((f, i) => (
            <li key={i}>
              <span>{f.title}</span>
              <small>{f.message}</small>
            </li>
          ))}
        </ul>
      )}
    </GlassSheet>
  )
}

/** Shows the summary whenever a playlist job finishes, whatever screen is open. */
export function PlaylistSummaryHost() {
  const [shown, setShown] = useState<Job | null>(null)
  const seen = useRef<Record<string, string>>({})

  useEffect(() => {
    const record = (jobs: Record<string, Job>) => {
      for (const j of Object.values(jobs)) {
        if (j.type !== 'playlist') continue
        const prev = seen.current[j.id]
        if (prev && prev !== 'done' && j.status === 'done') setShown(j)
        seen.current[j.id] = j.status
      }
    }
    record(useJobsStore.getState().jobs)
    return useJobsStore.subscribe((s) => record(s.jobs))
  }, [])

  return shown ? <PlaylistSummarySheet job={shown} onClose={() => setShown(null)} /> : null
}
