import { useEffect, useRef, useState } from 'react'
import { FileAudio, Library, Repeat, UploadCloud, X } from 'lucide-react'
import { FormatMenu } from '../components/FormatMenu'
import { GlassSheet } from '../components/GlassSheet'
import { SelectableTable, type Column } from '../components/SelectableTable'
import { useClient } from '../lib/engine'
import { useUiStore } from '../stores/uiStore'
import type { ConvertOptions, TrackRecord } from '../lib/types'
import './converter.css'

const AUDIO_EXT = ['mp3', 'm4a', 'aac', 'wav', 'aif', 'aiff', 'flac', 'ogg', 'opus', 'webm']
const isAudio = (name: string) => AUDIO_EXT.includes(name.split('.').pop()?.toLowerCase() ?? '')
const baseName = (p: string) => p.split(/[\\/]/).pop() ?? p

const PICK_COLUMNS: Column<TrackRecord>[] = [
  { key: 't', label: 'Título', render: (t) => <span className="cell-strong">{t.title}</span> },
  { key: 'a', label: 'Artista', render: (t) => t.artist },
  { key: 'f', label: 'Formato', width: '90px', render: (t) => t.format.toUpperCase() }
]

function LibraryPicker({ onPick, onClose }: { onPick(paths: string[]): void; onClose(): void }) {
  const client = useClient()
  const [rows, setRows] = useState<TrackRecord[] | null>(null)
  const [sel, setSel] = useState<Set<number>>(new Set())
  useEffect(() => {
    client.library().then((r) => setRows(r.filter((t) => !t.missing))).catch(() => setRows([]))
  }, [client])
  return (
    <GlassSheet
      title="Elegir de la biblioteca"
      wide
      onClose={onClose}
      actions={
        <>
          <button className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button
            className="btn btn-primary"
            disabled={sel.size === 0}
            onClick={() => onPick((rows ?? []).filter((t) => sel.has(t.id)).map((t) => t.path))}
          >
            Añadir ({sel.size})
          </button>
        </>
      }
    >
      {rows && rows.length === 0 && <p className="sheet-text">Tu biblioteca está vacía.</p>}
      {rows && rows.length > 0 && (
        <SelectableTable rows={rows} columns={PICK_COLUMNS} selected={sel} onSelect={setSel} rowId={(t) => t.id} rowLabel={(t) => t.title} />
      )}
    </GlassSheet>
  )
}

export function ConverterScreen() {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const navigate = useUiStore((s) => s.navigate)
  const [paths, setPaths] = useState<string[]>([])
  const [options, setOptions] = useState<ConvertOptions>({ format: 'mp3', quality: '320' })
  const [over, setOver] = useState(false)
  const [picking, setPicking] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const add = (incoming: string[]) => setPaths((p) => [...p, ...incoming.filter((x) => !p.includes(x))])

  const addFiles = (files: File[]) => {
    const audio = files.filter((f) => isAudio(f.name))
    const rejected = files.filter((f) => !isAudio(f.name))
    if (rejected.length) toast(`«${rejected[0].name}» no es un archivo de audio compatible`, 'error')
    add(audio.map((f) => window.oneforall.pathForFile(f)))
  }

  const convert = async () => {
    try {
      await client.convert(paths, options)
      toast(`Convirtiendo ${paths.length} ${paths.length === 1 ? 'archivo' : 'archivos'}`, 'success')
      setPaths([])
      navigate('descargas')
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  return (
    <section className="converter">
      <h1 className="screen-title">Conversor</h1>
      <div className="converter-grid">
        <div>
          <div
            data-testid="dropzone"
            className={`dropzone${over ? ' is-over' : ''}`}
            onDragOver={(e) => (e.preventDefault(), setOver(true))}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setOver(false)
              addFiles(Array.from(e.dataTransfer.files))
            }}
          >
            <UploadCloud size={36} strokeWidth={1.4} />
            <p>Arrastra archivos de audio aquí</p>
            <div className="dropzone-actions">
              <button className="btn btn-sm" onClick={() => fileInput.current?.click()}>
                <FileAudio size={14} />
                Elegir archivos
              </button>
              <button className="btn btn-sm" onClick={() => setPicking(true)}>
                <Library size={14} />
                Elegir de la biblioteca
              </button>
            </div>
            <input
              ref={fileInput}
              type="file"
              multiple
              hidden
              accept={AUDIO_EXT.map((e) => `.${e}`).join(',')}
              onChange={(e) => (addFiles(Array.from(e.target.files ?? [])), (e.target.value = ''))}
            />
          </div>
          {paths.length > 0 && (
            <ul className="file-list">
              {paths.map((p) => (
                <li key={p}>
                  <FileAudio size={16} />
                  <span title={p}>{baseName(p)}</span>
                  <button className="btn btn-ghost icon-btn btn-sm" aria-label={`Quitar ${baseName(p)}`} onClick={() => setPaths((ps) => ps.filter((x) => x !== p))}>
                    <X size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <aside className="converter-panel">
          <h2>Formato de salida</h2>
          <FormatMenu inline allowOriginal={false} value={options} onChange={setOptions} onClose={() => undefined} />
          <p className="converter-hint">El archivo original no se modifica. La copia se guarda junto a él.</p>
          <button className="btn btn-primary" disabled={paths.length === 0} onClick={convert}>
            <Repeat size={15} />
            Convertir ({paths.length})
          </button>
        </aside>
      </div>
      {picking && (
        <LibraryPicker
          onClose={() => setPicking(false)}
          onPick={(ps) => {
            add(ps)
            setPicking(false)
          }}
        />
      )}
    </section>
  )
}
