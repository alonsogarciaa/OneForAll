// Same rule as engine/djengine/discover/fit.py: compatible key (Camelot) and tempo within ±6 %, half and double included.
export type Fit = 'encaja' | 'cerca' | null

const TOLERANCE = 0.06

function split(code: string): [number, string] {
  return [parseInt(code.slice(0, -1), 10), code.slice(-1).toUpperCase()]
}

export function keysCompatible(a: string, b: string): boolean {
  const [na, la] = split(a)
  const [nb, lb] = split(b)
  if (Number.isNaN(na) || Number.isNaN(nb)) return false
  if (na === nb) return true // same key or relative major/minor
  return la === lb && [1, 11].includes((((na - nb) % 12) + 12) % 12)
}

function bpmOk(ref: number, bpm: number): boolean {
  return [1, 2, 0.5].some((m) => Math.abs(bpm * m - ref) / ref <= TOLERANCE)
}

export function fit(refBpm: number | null, refCamelot: string | null, bpm: number | null, camelot: string | null): Fit {
  const tempo = refBpm && bpm ? bpmOk(refBpm, bpm) : null
  const key = refCamelot && camelot ? keysCompatible(refCamelot, camelot) : null
  if (tempo && key) return 'encaja'
  if (tempo || key) return 'cerca'
  return null
}
