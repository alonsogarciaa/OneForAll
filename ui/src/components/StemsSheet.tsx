import { useState } from 'react'
import { Scissors } from 'lucide-react'
import { GlassSheet } from './GlassSheet'
import { useClient } from '../lib/engine'
import { DEFAULT_STEMS, STEM_IDS, STEM_LABEL, estimateLabel, estimateSeconds, type StemId } from '../lib/stems'
import { useUiStore } from '../stores/uiStore'
import './stems.css'

interface Props {
  paths: string[]
  durationS: number | null
  onClose(): void
  /** "After download" mode: return the choice instead of calling the engine. */
  onChoose?(stems: StemId[], karaoke: boolean): void
}

export function StemsSheet({ paths, durationS, onClose, onChoose }: Props) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const [picked, setPicked] = useState<Set<StemId>>(new Set(DEFAULT_STEMS))
  const [karaoke, setKaraoke] = useState(false)

  const toggle = (s: StemId) =>
    setPicked((prev) => {
      const next = new Set(prev)
      next.has(s) ? next.delete(s) : next.add(s)
      return next
    })

  const chosen = STEM_IDS.filter((s) => picked.has(s))

  const go = async () => {
    if (onChoose) {
      onChoose(chosen, karaoke)
      onClose()
      return
    }
    try {
      await client.separate(paths, chosen, karaoke)
      toast(paths.length === 1 ? 'Separando stems…' : `Separando stems de ${paths.length} canciones`, 'success')
      onClose()
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  const total = (durationS ?? 240) * paths.length

  return (
    <GlassSheet
      title="Separar stems"
      onClose={onClose}
      actions={
        <>
          <button className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn btn-primary" disabled={chosen.length === 0} onClick={go}>
            <Scissors size={15} />
            Separar
          </button>
        </>
      }
    >
      <div className="stem-picks">
        {STEM_IDS.map((s) => (
          <label key={s} className="stem-pick">
            <input type="checkbox" aria-label={STEM_LABEL[s]} checked={picked.has(s)} onChange={() => toggle(s)} />
            <span>{STEM_LABEL[s]}</span>
          </label>
        ))}
      </div>
      <div className="stem-karaoke">
        <span>
          Separar voz principal y coros
          <small>Añade dos archivos más a partir de la voz.</small>
        </span>
        <button role="switch" aria-checked={karaoke} aria-label="Separar voz principal y coros" className="switch" onClick={() => setKaraoke((v) => !v)}>
          <span />
        </button>
      </div>
      <p className="sheet-text stem-estimate">{estimateLabel(estimateSeconds(total))}</p>
    </GlassSheet>
  )
}
