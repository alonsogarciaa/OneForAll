// Song sections: labels and colours (same as djengine/prep/sections.py) and pure edit helpers.
import type { Section, SectionLabel } from './types'

export const SECTION_LABELS: SectionLabel[] = ['Intro', 'Verso', 'Subida', 'Estribillo/Drop', 'Bajón', 'Outro']

const COLORS: Record<SectionLabel, [number, number, number]> = {
  Intro: [142, 142, 147],
  Verso: [10, 132, 255],
  Subida: [255, 214, 10],
  'Estribillo/Drop': [255, 69, 58],
  Bajón: [191, 90, 242],
  Outro: [99, 99, 102]
}

export function sectionColor(label: string): string {
  const c = COLORS[label as SectionLabel] ?? [255, 255, 255]
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`
}

const round = (t: number) => Math.round(t * 1000) / 1000
const plain = (s: Section): Section => ({ start: s.start, end: s.end, label: s.label })

export function rename(list: Section[], i: number, label: SectionLabel): Section[] {
  return list.map((s, k) => (k === i ? { ...plain(s), label } : plain(s)))
}

/** Move the start of section i (and the end of i-1), snapped to the nearest bar; never shorter than one bar. */
export function moveBoundary(list: Section[], i: number, t: number, snapBars: number[] | null): Section[] {
  if (i <= 0 || i >= list.length) return list.map(plain)
  const bar = snapBars && snapBars.length > 1 ? snapBars[1] - snapBars[0] : 0.5
  let to = t
  if (snapBars && snapBars.length) to = snapBars.reduce((best, b) => (Math.abs(b - t) < Math.abs(best - t) ? b : best), snapBars[0])
  to = Math.min(list[i].end - bar, Math.max(list[i - 1].start + bar, to))
  to = round(to)
  return list.map((s, k) => (k === i ? { ...plain(s), start: to } : k === i - 1 ? { ...plain(s), end: to } : plain(s)))
}

export function mergeNext(list: Section[], i: number): Section[] {
  if (i < 0 || i >= list.length - 1) return list.map(plain)
  const out = list.map(plain)
  out[i] = { ...out[i], end: out[i + 1].end }
  out.splice(i + 1, 1)
  return out
}

export function splitAt(list: Section[], t: number): Section[] {
  const i = list.findIndex((s) => s.start < t && t < s.end)
  if (i < 0) return list.map(plain)
  const out = list.map(plain)
  out.splice(i, 1, { ...out[i], end: round(t) }, { ...out[i], start: round(t) })
  return out
}

/** Delete section i: the previous one absorbs it (removing the first extends the next one to 0). */
export function remove(list: Section[], i: number): Section[] {
  if (list.length <= 1) return []
  const out = list.map(plain)
  if (i === 0) out[1] = { ...out[1], start: 0 }
  else out[i - 1] = { ...out[i - 1], end: out[i].end }
  out.splice(i, 1)
  return out
}
