import { useEffect, useRef } from 'react'
import { Info } from 'lucide-react'
import { FORMAT_NAMES, LOSSLESS, MP3_QUALITIES } from '../lib/format'
import type { ConvertOptions, FormatId } from '../lib/types'

interface Props {
  value: ConvertOptions
  onChange(v: ConvertOptions): void
  onClose(): void
  /** Hide "Original" (it only makes sense for downloads). */
  allowOriginal?: boolean
  /** Render in place (no popover behaviour), e.g. inside the converter panel. */
  inline?: boolean
  /** When given, adds the "Stems" block: download then separate. stems=null opens the picker. */
  onStems?(stems: string[] | null): void
}

const FORMATS = Object.keys(FORMAT_NAMES) as FormatId[]

export function FormatMenu({ value, onChange, onClose, allowOriginal = true, inline = false, onStems }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const lossless = LOSSLESS.includes(value.format)

  useEffect(() => {
    if (inline) return
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && onClose()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose, inline])

  const setFormat = (format: FormatId) =>
    onChange({ format, quality: format === 'mp3' ? '320' : null, sample_rate: null, bit_depth: LOSSLESS.includes(format) ? 16 : null })

  return (
    <div
      ref={ref}
      className={inline ? 'format-inline' : 'format-menu glass'}
      role={inline ? 'group' : 'dialog'}
      aria-label={inline ? 'Formato de salida' : 'Formato de descarga'}
      onClick={(e) => e.stopPropagation()}
    >
      <label className="format-field">
        <span>Formato</span>
        <select className="field" aria-label="Formato" value={value.format} onChange={(e) => setFormat(e.target.value as FormatId)}>
          {FORMATS.filter((f) => allowOriginal || f !== 'original').map((f) => (
            <option key={f} value={f}>
              {f === 'original' ? 'Original (sin convertir)' : FORMAT_NAMES[f]}
            </option>
          ))}
        </select>
      </label>
      {value.format === 'mp3' && (
        <label className="format-field">
          <span>Calidad</span>
          <select className="field" aria-label="Calidad" value={value.quality ?? '320'} onChange={(e) => onChange({ ...value, quality: e.target.value })}>
            {MP3_QUALITIES.map((q) => (
              <option key={q} value={q}>
                {q === 'v0' ? 'VBR V0' : `${q} kbps`}
              </option>
            ))}
          </select>
        </label>
      )}
      {lossless && (
        <>
          <label className="format-field">
            <span>Frecuencia</span>
            <select
              className="field"
              aria-label="Frecuencia"
              value={value.sample_rate ?? ''}
              onChange={(e) => onChange({ ...value, sample_rate: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">Igual que el origen</option>
              <option value="44100">44,1 kHz</option>
              <option value="48000">48 kHz</option>
              <option value="96000">96 kHz</option>
            </select>
          </label>
          <label className="format-field">
            <span>Profundidad</span>
            <select
              className="field"
              aria-label="Profundidad"
              value={value.bit_depth ?? 16}
              onChange={(e) => onChange({ ...value, bit_depth: Number(e.target.value) })}
            >
              <option value="16">16 bit</option>
              <option value="24">24 bit</option>
            </select>
          </label>
          <p className="format-note">
            <Info size={15} />
            Convertir audio de YouTube a un formato sin pérdida no aumenta su calidad.
          </p>
        </>
      )}
      {onStems && (
        <div className="format-stems">
          <span>Stems</span>
          <div className="stem-buttons">
            <button className="btn btn-sm" onClick={() => (onStems(['vocals']), onClose())}>Solo voz</button>
            <button className="btn btn-sm" onClick={() => (onStems(['drums']), onClose())}>Solo batería</button>
            <button className="btn btn-sm" onClick={() => (onStems(['bass']), onClose())}>Solo bajo</button>
            <button className="btn btn-sm" onClick={() => (onStems(['vocals', 'drums', 'bass', 'guitar', 'piano', 'other']), onClose())}>
              Todos los stems
            </button>
            <button className="btn btn-sm btn-ghost" onClick={() => (onStems(null), onClose())}>Elegir…</button>
          </div>
        </div>
      )}
    </div>
  )
}
