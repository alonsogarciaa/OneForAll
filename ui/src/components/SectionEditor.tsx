import { useClient } from '../lib/engine'
import { mergeNext, moveBoundary, remove, rename, sectionColor, SECTION_LABELS, splitAt } from '../lib/sections'
import { formatDuration } from '../lib/format'
import { useUiStore } from '../stores/uiStore'
import type { Section, SectionLabel } from '../lib/types'

interface Props {
  path: string
  sections: Section[]
  /** Bar start times: section starts snap to them. */
  bars: number[]
  position: number
  onChange(sections: Section[]): void
}

export function SectionEditor({ path, sections, bars, position, onChange }: Props) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)

  const save = async (next: Section[] | null) => {
    try {
      const r = await client.putSections(path, next)
      onChange(r.sections)
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  return (
    <section className="ds-sections" aria-label="Secciones">
      {sections.length === 0 && <p className="ds-sub">Sin secciones</p>}
      <ul>
        {sections.map((s, i) => (
          <li key={`${s.start}-${i}`}>
            <span className="ds-section-dot" style={{ background: sectionColor(s.label) }} aria-hidden />
            <select
              className="field"
              aria-label={`Etiqueta de la sección ${i + 1}`}
              value={s.label}
              onChange={(e) => void save(rename(sections, i, e.target.value as SectionLabel))}
            >
              {SECTION_LABELS.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
            <span className="tabular ds-sub">
              {formatDuration(s.start)}–{formatDuration(s.end)}
            </span>
            <button
              className="btn btn-sm"
              disabled={i === 0}
              title="Mueve el inicio al cabezal (ajustado a compás; con Alt, libre)"
              onClick={(e) => void save(moveBoundary(sections, i, position, e.altKey ? null : bars))}
            >
              Inicio al cabezal
            </button>
            <button className="btn btn-sm" disabled={i === sections.length - 1} onClick={() => void save(mergeNext(sections, i))}>
              Unir con la siguiente
            </button>
            <button className="btn btn-sm btn-ghost" onClick={() => void save(remove(sections, i))}>
              Borrar
            </button>
          </li>
        ))}
      </ul>
      <div className="ds-sections-actions">
        {sections.length > 0 && (
          <button className="btn btn-sm" onClick={() => void save(splitAt(sections, position))}>
            Partir en el cabezal
          </button>
        )}
        <button className="btn btn-sm btn-ghost" onClick={() => void save(null)}>
          Volver al automático
        </button>
      </div>
    </section>
  )
}
