import { useCallback, useEffect, useState } from 'react'
import { FolderOpen, Library, Search } from 'lucide-react'
import { SelectableTable, type Column } from '../components/SelectableTable'
import { useClient } from '../lib/engine'
import { useUiStore } from '../stores/uiStore'
import { useJobsStore } from '../stores/jobsStore'
import { formatDate, formatDuration, formatViews, FORMAT_NAMES } from '../lib/format'
import type { FormatId, TrackRecord } from '../lib/types'
import './tables.css'

const COLUMNS: Column<TrackRecord>[] = [
  {
    key: 'title',
    label: 'Título',
    render: (t) => (
      <span className="cell-title">
        <span className="cell-strong">{t.title}</span>
        {t.missing && <span className="badge badge-warn">No encontrado</span>}
      </span>
    )
  },
  { key: 'artist', label: 'Artista', render: (t) => t.artist },
  { key: 'duration', label: 'Duración', width: '84px', align: 'right', render: (t) => <span className="tabular">{t.duration_s != null ? formatDuration(t.duration_s) : '—'}</span> },
  { key: 'views', label: 'Visualizaciones', width: '120px', align: 'right', render: (t) => <span className="tabular">{t.views != null ? formatViews(t.views) : '—'}</span> },
  { key: 'format', label: 'Formato', width: '90px', render: (t) => FORMAT_NAMES[t.format as FormatId] ?? t.format.toUpperCase() },
  { key: 'added', label: 'Añadida', width: '150px', render: (t) => <span className="tabular">{formatDate(t.added_at)}</span> },
  {
    key: 'open',
    label: '',
    width: '44px',
    render: (t) =>
      !t.missing && (
        <button
          className="btn btn-ghost icon-btn btn-sm"
          aria-label={`Mostrar ${t.title} en carpeta`}
          onClick={(e) => (e.stopPropagation(), window.oneforall.showInFolder(t.path))}
        >
          <FolderOpen size={15} />
        </button>
      )
  }
]

export function LibraryScreen() {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const doneCount = useJobsStore((s) => Object.values(s.jobs).filter((j) => j.status === 'done').length)
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<TrackRecord[] | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())

  const load = useCallback(() => {
    client.library(q).then(setRows).catch((e) => toast(e.message, 'error'))
  }, [client, q, toast])

  useEffect(() => {
    const t = setTimeout(load, 200)
    return () => clearTimeout(t)
  }, [load, doneCount])

  return (
    <section>
      <div className="screen-head">
        <h1 className="screen-title">Biblioteca</h1>
        <label className="filter">
          <Search size={15} />
          <input className="field" placeholder="Filtrar por título, artista o álbum" aria-label="Filtrar biblioteca" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
      </div>
      {rows && rows.length === 0 && (
        <div className="empty">
          <Library size={40} strokeWidth={1.4} />
          <p>{q ? `Nada coincide con "${q}"` : 'Tu biblioteca está vacía. Descarga algo desde Buscar.'}</p>
        </div>
      )}
      {rows && rows.length > 0 && (
        <SelectableTable
          rows={rows}
          columns={COLUMNS}
          selected={selected}
          onSelect={setSelected}
          rowId={(t) => t.id}
          rowLabel={(t) => t.title}
          onActivate={(t) => !t.missing && window.oneforall.openPath(t.path)}
          rowClass={(t) => (t.missing ? 'row-missing' : undefined)}
        />
      )}
    </section>
  )
}
