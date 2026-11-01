import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'

interface Props {
  title: string
  onClose(): void
  children: ReactNode
  actions?: ReactNode
  wide?: boolean
}

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'

export function GlassSheet({ title, onClose, children, actions, wide }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    const nodes = ref.current?.querySelectorAll<HTMLElement>(FOCUSABLE)
    // Focus the first action rather than the close button, so Enter does the expected thing.
    const first = Array.from(nodes ?? []).find((n) => !n.classList.contains('sheet-close')) ?? nodes?.[0]
    first?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      } else if (e.key === 'Tab' && ref.current) {
        const list = Array.from(ref.current.querySelectorAll<HTMLElement>(FOCUSABLE))
        if (list.length === 0) return
        const i = list.indexOf(document.activeElement as HTMLElement)
        const next = e.shiftKey ? (i <= 0 ? list.length - 1 : i - 1) : i === list.length - 1 ? 0 : i + 1
        list[next].focus()
        e.preventDefault()
      }
    }
    document.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('keydown', onKey, true)
      prev?.focus?.()
    }
  }, [onClose])

  return (
    <div className="sheet-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={ref}
        className="sheet glass"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={wide ? { width: 'min(720px, calc(100vw - 48px))' } : undefined}
      >
        <div className="sheet-header">
          <h2>{title}</h2>
          <button className="btn btn-ghost icon-btn sheet-close" aria-label="Cerrar" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <div className="sheet-body">{children}</div>
        {actions && <div className="sheet-actions">{actions}</div>}
      </div>
    </div>
  )
}
