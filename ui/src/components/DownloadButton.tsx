import { useState } from 'react'
import { ChevronDown, Download } from 'lucide-react'
import { FormatMenu } from './FormatMenu'
import { formatLabel } from '../lib/format'
import type { ConvertOptions } from '../lib/types'

interface Props {
  options: ConvertOptions
  onOptions(o: ConvertOptions): void
  onDownload(): void
  label?: string
  busy?: boolean
  /** Rows use the quiet variant so a long result list is not a wall of blue. */
  variant?: 'primary' | 'subtle'
  onStems?(stems: string[] | null): void
}

/** Split pill: main part downloads with the current format, chevron opens the format menu. */
export function DownloadButton({ options, onOptions, onDownload, label = 'Descargar', busy, variant = 'primary', onStems }: Props) {
  const [open, setOpen] = useState(false)
  const tone = variant === 'primary' ? 'btn-primary' : 'btn-subtle'
  return (
    <div className={`split-btn split-${variant}`} onClick={(e) => e.stopPropagation()}>
      <button className={`btn ${tone} btn-sm split-main`} onClick={onDownload} disabled={busy} aria-label={`${label} en ${formatLabel(options)}`}>
        <Download size={15} />
        {label}
        <span className="split-format">{formatLabel(options)}</span>
      </button>
      <button className={`btn ${tone} btn-sm split-chevron`} aria-label="Elegir formato" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <ChevronDown size={15} />
      </button>
      {open && <FormatMenu value={options} onChange={onOptions} onClose={() => setOpen(false)} onStems={onStems} />}
    </div>
  )
}
