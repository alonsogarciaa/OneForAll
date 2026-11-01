import { Download } from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'
import { JobRow, PlaylistJobRow } from '../components/JobRow'
import { allJobs, useJobsStore } from '../stores/jobsStore'
import './downloads.css'

export function DownloadsScreen() {
  // Top-level jobs, newest first; playlist children render under their parent.
  const jobs = useJobsStore(useShallow((s) => allJobs(s).filter((j) => !j.parent_id).reverse()))
  return (
    <section>
      <h1 className="screen-title">Descargas</h1>
      {jobs.length === 0 ? (
        <div className="empty">
          <Download size={40} strokeWidth={1.4} />
          <p>No hay descargas todavía</p>
        </div>
      ) : (
        <div className="job-list">{jobs.map((j) => (j.type === 'playlist' ? <PlaylistJobRow key={j.id} job={j} /> : <JobRow key={j.id} job={j} />))}</div>
      )}
    </section>
  )
}
