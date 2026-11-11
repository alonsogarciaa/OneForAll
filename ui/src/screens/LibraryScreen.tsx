import { useCallback, useEffect, useRef, useState } from 'react'
import { AudioLines, FileAudio, FolderOpen, Layers, Library, Scissors, Search } from 'lucide-react'
import { KeyChip } from '../components/KeyChip'
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
        {t.enhanced && <span className="badge badge-muted">Mejorado</span>}
      </span>
    )
  },
  { key: 'artist', label: 'Artista', render: (t) => t.artist },
  { key: 'bpm', label: 'BPM', width: '62px', align: 'right', render: (t) => <span className="tabular cell-strong">{t.bpm != null ? t.bpm.toFixed(1) : '—'}</span> },
  { key: 'key', label: 'Tonalidad', width: '78px', render: (t) => <KeyChip camelot={t.camelot} /> },
  { key: 'stems', label: 'Stems', width: '50px', render: (t) => (t.has_stems ? <Layers size={15} aria-label="Tiene stems" /> : null) },
  { key: 'lufs', label: 'LUFS', width: '58px', align: 'right', render: (t) => <span className="tabular">{t.lufs != null ? t.lufs.toFixed(1) : '—'}</span> },
  { key: 'duration', label: 'Duración', width: '72px', align: 'right', render: (t) => <span className="tabular">{t.duration_s != null ? formatDuration(t.duration_s) : '—'}</span> },
  { key: 'views', label: 'Vistas', width: '64px', align: 'right', render: (t) => <span className="tabular">{t.views != null ? formatViews(t.views) : '—'}</span> },
  { key: 'format', label: 'Formato', width: '70px', render: (t) => FORMAT_NAMES[t.format as FormatId] ?? t.format.toUpperCase() },
  { key: 'added', label: 'Añadida', width: '140px', render: (t) => <span className="tabular">{formatDate(t.added_at)}</span> },
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
  const fileInput = useRef<HTMLInputElement>(null)
  const openData = useUiStore((s) => s.openData)
  const openStems = useUiStore((s) => s.openStems)
  const openRetempo = useUiStore((s) => s.openRetempo)
  const openEnhance = useUiStore((s) => s.openEnhance)
  const openVideoExport = useUiStore((s) => s.openVideoExport)
  const openDjExport = useUiStore((s) => s.openDjExport)

  const load = useCallback(() => {
    client.library(q).then(setRows).catch((e) => toast(e.message, 'error'))
  }, [client, q, toast])

  useEffect(() => {
    const t = setTimeout(load, 200)
    return () => clearTimeout(t)
  }, [load, doneCount])

  const analyze = async (paths: string[]) => {
    try {
      await client.analyze(paths)
      toast(paths.length === 1 ? 'Analizando…' : `Analizando ${paths.length} canciones`, 'success')
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  return (
    <section>
      <div className="screen-head">
        <h1 className="screen-title">Biblioteca</h1>
        <div className="toolbar">
          <button
            className="btn btn-sm"
            disabled={selected.size === 0}
            onClick={() => analyze((rows ?? []).filter((t) => selected.has(t.id) && !t.missing).map((t) => t.path))}
          >
            <AudioLines size={14} />
            Analizar seleccionadas ({selected.size})
          </button>
          <button
            className="btn btn-sm"
            disabled={selected.size === 0}
            onClick={() => {
              const picked = (rows ?? []).filter((t) => selected.has(t.id) && !t.missing)
              openStems(picked.map((t) => t.path), picked.reduce((a, t) => a + (t.duration_s ?? 240), 0) / Math.max(1, picked.length))
            }}
          >
            <Scissors size={14} />
            Separar stems ({selected.size})
          </button>
          <button
            className="btn btn-sm"
            disabled={selected.size !== 1}
            onClick={() => {
              const t = (rows ?? []).find((x) => selected.has(x.id) && !x.missing)
              if (t) openRetempo(t.path)
            }}
          >
            Cambiar BPM y tono…
          </button>
          <button
            className="btn btn-sm"
            disabled={selected.size === 0}
            onClick={() => {
              const picked = (rows ?? []).filter((t) => selected.has(t.id) && !t.missing)
              if (picked.length) openEnhance(picked.map((t) => ({ path: t.path, enhanced: !!t.enhanced })))
            }}
          >
            Mejorar audio…
          </button>
          <button
            className="btn btn-sm"
            disabled={selected.size !== 1}
            onClick={() => useUiStore.getState().openDiscover([...selected][0])}
          >
            Parecidas
          </button>
          <button className="btn btn-sm" disabled={selected.size === 0} onClick={() => openVideoExport([...selected])}>
            Exportar vídeo…
          </button>
          <button className="btn btn-sm" onClick={() => openDjExport(selected.size ? [...selected] : null)}>
            Exportar a…
          </button>
          <button className="btn btn-sm" onClick={() => fileInput.current?.click()}>
            <FileAudio size={14} />
            Analizar archivo…
          </button>
          <input
            ref={fileInput}
            type="file"
            hidden
            accept=".mp3,.m4a,.aac,.wav,.aif,.aiff,.flac,.ogg,.opus,.webm"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) openData(window.oneforall.pathForFile(f)) // the data sheet analyses it if needed
              e.target.value = ''
            }}
          />
        </div>
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
          onActivate={(t) => !t.missing && openData(t.path)}
          rowClass={(t) => (t.missing ? 'row-missing' : undefined)}
        />
      )}
    </section>
  )
}
