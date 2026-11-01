import { useRef, type ReactNode } from 'react'

export interface Column<T> {
  key: string
  label: string
  render(row: T): ReactNode
  width?: string
  align?: 'left' | 'right'
}

interface Props<T> {
  rows: T[]
  columns: Column<T>[]
  selected: Set<number>
  onSelect(ids: Set<number>): void
  rowId(r: T): number
  rowLabel(r: T): string
  onActivate?(r: T): void
  rowClass?(r: T): string | undefined
}

/** Table with checkbox selection: click, Ctrl+click toggles, Shift+click selects a range. */
export function SelectableTable<T>({ rows, columns, selected, onSelect, rowId, rowLabel, onActivate, rowClass }: Props<T>) {
  const anchor = useRef<number | null>(null)
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(rowId(r)))

  const toggle = (id: number) => {
    const next = new Set(selected)
    next.has(id) ? next.delete(id) : next.add(id)
    anchor.current = id
    onSelect(next)
  }

  const clickRow = (e: React.MouseEvent, id: number) => {
    if (e.shiftKey && anchor.current !== null) {
      const ids = rows.map(rowId)
      const [a, b] = [ids.indexOf(anchor.current), ids.indexOf(id)].sort((x, y) => x - y)
      onSelect(new Set([...selected, ...ids.slice(a, b + 1)]))
    } else if (e.ctrlKey || e.metaKey) {
      toggle(id)
    } else {
      anchor.current = id
      onSelect(new Set([id]))
    }
  }

  const template = ['36px', ...columns.map((c) => c.width ?? 'minmax(0, 1fr)')].join(' ')

  return (
    <div className="stable" role="table">
      <div className="stable-row stable-head" role="row" style={{ gridTemplateColumns: template }}>
        <span role="columnheader">
          <input
            type="checkbox"
            aria-label="Seleccionar todo"
            checked={allSelected}
            onChange={() => onSelect(allSelected ? new Set() : new Set(rows.map(rowId)))}
          />
        </span>
        {columns.map((c) => (
          <span key={c.key} role="columnheader" style={{ textAlign: c.align }}>
            {c.label}
          </span>
        ))}
      </div>
      {rows.map((r) => {
        const id = rowId(r)
        return (
          <div
            key={id}
            role="row"
            aria-selected={selected.has(id)}
            className={`stable-row${rowClass?.(r) ? ` ${rowClass(r)}` : ''}`}
            style={{ gridTemplateColumns: template }}
            onClick={(e) => clickRow(e, id)}
            onDoubleClick={() => onActivate?.(r)}
          >
            <span role="cell" onClick={(e) => e.stopPropagation()}>
              <input type="checkbox" aria-label={`Seleccionar ${rowLabel(r)}`} checked={selected.has(id)} onChange={() => toggle(id)} />
            </span>
            {columns.map((c) => (
              <span key={c.key} role="cell" style={{ textAlign: c.align }}>
                {c.render(r)}
              </span>
            ))}
          </div>
        )
      })}
    </div>
  )
}
