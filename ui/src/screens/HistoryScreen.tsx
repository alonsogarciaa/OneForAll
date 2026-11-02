import { useCallback, useEffect, useState } from 'react'
import { History, Scissors, Trash2 } from 'lucide-react'
import { SelectableTable, type Column } from '../components/SelectableTable'
import { KeyChip } from '../components/KeyChip'
import { GlassSheet } from '../components/GlassSheet'
import { useClient } from '../lib/engine'
import { useUiStore } from '../stores/uiStore'
import { useJobsStore } from '../stores/jobsStore'
import { formatDate } from '../lib/format'
import type { HistoryEntry } from '../lib/types'
import './tables.css'

const COLUMNS: Column<HistoryEntry>[] = [
  { key: 'title', label: 'Título', render: (h) => <span className="cell-strong">{h.title}</span> },
  { key: 'artist', label: 'Artista', render: (h) => h.artist },
  { key: 'bpm', label: 'BPM', width: '62px', align: 'right', render: (h) => <span className="tabular">{h.bpm != null ? h.bpm.toFixed(1) : '—'}</span> },
  { key: 'key', label: 'Tonalidad', width: '78px', render: (h) => <KeyChip camelot={h.camelot} /> },
  { key: 'action', label: 'Acción', width: '120px', render: (h) => (h.action === 'convert' ? 'Conversión' : 'Descarga') },
  {
    key: 'status',
    label: 'Estado',
    width: '110px',
    render: (h) => <span className={h.status === 'done' ? 'txt-ok' : 'txt-err'}>{h.status === 'done' ? 'Completada' : 'Fallida'}</span>
  },
  { key: 'at', label: 'Fecha', width: '150px', render: (h) => <span className="tabular">{formatDate(h.at)}</span> }
]

export function HistoryScreen() {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const finishedCount = useJobsStore((s) => Object.values(s.jobs).filter((j) => j.status === 'done' || j.status === 'failed').length)
  const [rows, setRows] = useState<HistoryEntry[] | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [confirmAll, setConfirmAll] = useState(false)
  const openData = useUiStore((s) => s.openData)
  const openStems = useUiStore((s) => s.openStems)

  const load = useCallback(() => {
    client.history().then(setRows).catch((e) => toast(e.message, 'error'))
  }, [client, toast])

  useEffect(load, [load, finishedCount])

  const remove = async (ids: number[] | 'all') => {
    try {
      await client.deleteHistory(ids)
      setSelected(new Set())
      setConfirmAll(false)
      load()
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  return (
    <section>
      <div className="screen-head">
        <h1 className="screen-title">Historial</h1>
        <div className="toolbar">
          <button
            className="btn btn-sm"
            disabled={!(rows ?? []).some((h) => selected.has(h.id) && h.path)}
            onClick={() => openStems((rows ?? []).filter((h) => selected.has(h.id) && h.path).map((h) => h.path!))}
          >
            <Scissors size={14} />
            Separar stems
          </button>
          <button className="btn btn-sm" disabled={selected.size === 0} onClick={() => remove([...selected])}>
            <Trash2 size={14} />
            Borrar seleccionadas ({selected.size})
          </button>
          <button className="btn btn-sm btn-danger" disabled={!rows?.length} onClick={() => setConfirmAll(true)}>
            Borrar todo
          </button>
        </div>
      </div>
      {rows && rows.length === 0 && (
        <div className="empty">
          <History size={40} strokeWidth={1.4} />
          <p>Aquí aparecerán tus descargas y conversiones</p>
        </div>
      )}
      {rows && rows.length > 0 && (
        <SelectableTable
          rows={rows}
          columns={COLUMNS}
          selected={selected}
          onSelect={setSelected}
          rowId={(h) => h.id}
          rowLabel={(h) => h.title}
          onActivate={(h) => h.path && openData(h.path)}
        />
      )}
      {confirmAll && (
        <GlassSheet
          title="Borrar historial"
          onClose={() => setConfirmAll(false)}
          actions={
            <>
              <button className="btn" onClick={() => setConfirmAll(false)}>
                Cancelar
              </button>
              <button className="btn btn-primary" onClick={() => remove('all')}>
                Borrar todo
              </button>
            </>
          }
        >
          <p className="sheet-text">¿Borrar todo el historial? Los archivos no se borran.</p>
        </GlassSheet>
      )}
    </section>
  )
}
