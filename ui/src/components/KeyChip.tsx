import { camelotColor, displayKey } from '../lib/camelot'

/** Camelot code on its wheel colour; the full name («8A · Lam») shows on hover. */
export function KeyChip({ camelot }: { camelot: string | null | undefined }) {
  if (!camelot) return <span className="key-empty">—</span>
  return (
    <span className="key-chip tabular" style={{ background: camelotColor(camelot) }} title={displayKey(camelot)}>
      {camelot}
    </span>
  )
}
