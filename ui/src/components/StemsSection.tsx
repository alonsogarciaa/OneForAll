import { useCallback, useEffect, useRef, useState } from 'react'
import { FolderOpen, GripVertical, Package, Pause, Play, Scissors, X } from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'
import { useClient } from '../lib/engine'
import { STEM_LABEL } from '../lib/stems'
import { useJobsStore, isFinal } from '../stores/jobsStore'
import { useUiStore } from '../stores/uiStore'
import './stems.css'

interface StemFile {
  stem: string
  file: string
  size_bytes: number
}

const ORDER = ['vocals', 'lead_vocals', 'backing_vocals', 'drums', 'bass', 'guitar', 'piano', 'other']
const mb = (b: number) => `${(b / 1_048_576).toLocaleString('es-ES', { maximumFractionDigits: 1 })} MB`

export function StemsSection({ path, durationS }: { path: string; durationS: number | null }) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const openStems = useUiStore((s) => s.openStems)
  const [stems, setStems] = useState<StemFile[] | null>(null)
  const [folder, setFolder] = useState<string | null>(null)
  const [playing, setPlaying] = useState<string | null>(null)
  const audio = useRef<HTMLAudioElement>(null)
  // a running stems job for this file (to show progress and refresh when it ends)
  const job = useJobsStore(
    useShallow((s) => Object.values(s.jobs).find((j) => j.type === 'stems' && j.payload?.paths?.[0] === path && !isFinal(j)) ?? null)
  )
  const doneCount = useJobsStore((s) => Object.values(s.jobs).filter((j) => j.type === 'stems' && j.status === 'done').length)

  const load = useCallback(() => {
    client
      .getStems(path)
      .then((r) => {
        const sorted = [...r.stems].sort((a, b) => ORDER.indexOf(a.stem) - ORDER.indexOf(b.stem))
        setStems(sorted)
        setFolder(r.folder)
        window.oneforall.allowDrag(sorted.map((s) => s.file))
      })
      .catch((e) => toast(e.message, 'error'))
  }, [client, path, toast])

  useEffect(load, [load, doneCount])

  const toggle = (file: string) => {
    const a = audio.current
    if (!a) return
    if (playing === file) {
      a.pause()
      setPlaying(null)
      return
    }
    a.src = client.audioUrl(file)
    a.play().then(() => setPlaying(file)).catch(() => toast('No se puede reproducir este stem', 'error'))
  }

  const zip = async () => {
    try {
      const r = await client.zipStems(path)
      window.oneforall.showInFolder(r.zip)
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  return (
    <section className="ds-stems" aria-label="Stems">
      <h3 className="ds-section-title">Stems</h3>
      {job && (
        <div className="ds-progress">
          <span>{job.stage === 'separating' ? `Separando ${Math.round(job.pct)} %` : 'Preparando…'}</span>
          <div className="progress"><div className="is-animating" style={{ width: `${job.pct}%` }} /></div>
          <button className="btn btn-sm" onClick={() => client.cancelJob(job.id)}>
            <X size={14} />
            Cancelar
          </button>
        </div>
      )}
      {stems && stems.length === 0 && !job && (
        <div className="stems-empty">
          <span>Aún no hay stems</span>
          <button className="btn btn-sm" onClick={() => openStems([path], durationS)}>
            <Scissors size={14} />
            Separar stems…
          </button>
        </div>
      )}
      {stems && stems.length > 0 && (
        <>
          <ul className="stem-list">
            {stems.map((s) => (
              <li
                key={s.stem}
                draggable
                onDragStart={(e) => {
                  e.preventDefault()
                  window.oneforall.startDrag(s.file)
                }}
                title="Arrastra a tu DAW o a una carpeta"
              >
                <GripVertical size={15} className="stem-grip" aria-hidden />
                <button className="btn btn-ghost icon-btn btn-sm" aria-label={`${playing === s.file ? 'Pausar' : 'Reproducir'} ${STEM_LABEL[s.stem]}`} onClick={() => toggle(s.file)}>
                  {playing === s.file ? <Pause size={15} /> : <Play size={15} />}
                </button>
                <span className="stem-name">{STEM_LABEL[s.stem] ?? s.stem}</span>
                <span className="stem-size tabular">{mb(s.size_bytes)}</span>
              </li>
            ))}
          </ul>
          <div className="stem-actions">
            <button className="btn btn-sm" onClick={() => folder && window.oneforall.openPath(folder)}>
              <FolderOpen size={14} />
              Mostrar carpeta
            </button>
            <button className="btn btn-sm" onClick={zip}>
              <Package size={14} />
              Exportar zip
            </button>
            <button className="btn btn-sm btn-ghost" onClick={() => openStems([path], durationS)}>
              <Scissors size={14} />
              Separar más…
            </button>
          </div>
        </>
      )}
      <audio ref={audio} preload="none" onEnded={() => setPlaying(null)} />
    </section>
  )
}
