import { camelotShift } from './camelot'
import type { ConvertOptions, FormatId } from './types'

export function formatDuration(s: number): string {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  const ss = String(sec).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}

function compact(n: number): string {
  const rounded = n >= 10 ? Math.round(n) : Math.round(n * 10) / 10
  return String(rounded).replace('.', ',')
}

export function formatViews(n: number): string {
  if (n >= 1e9) return `${compact(n / 1e9)} mil M`
  if (n >= 1e6) return `${compact(n / 1e6)} M`
  if (n >= 1e3) return `${compact(n / 1e3)} K`
  return String(n)
}

export const FORMAT_NAMES: Record<FormatId, string> = {
  mp3: 'MP3',
  aac: 'AAC',
  alac: 'ALAC',
  opus: 'Opus',
  ogg: 'OGG',
  flac: 'FLAC',
  wav: 'WAV',
  aiff: 'AIFF',
  original: 'Original'
}

export const LOSSLESS: FormatId[] = ['alac', 'flac', 'wav', 'aiff']
export const MP3_QUALITIES = ['320', '256', '192', '128', 'v0']

export function formatLabel(o: ConvertOptions): string {
  const name = FORMAT_NAMES[o.format]
  if (o.format === 'mp3') return `${name} ${(o.quality ?? '320').toUpperCase()}`
  if (LOSSLESS.includes(o.format) && o.bit_depth) return `${name} ${o.bit_depth}-bit`
  return name
}

const DATE_FMT = new Intl.DateTimeFormat('es-ES', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })

export function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : DATE_FMT.format(d)
}

/** Python's round() to 1 decimal (half to even), so names match the engine exactly. */
function round1(x: number): number {
  const v = x * 10
  const f = Math.floor(v)
  const d = v - f
  const r = Math.abs(d - 0.5) < 1e-9 ? (f % 2 === 0 ? f : f + 1) : Math.round(v)
  return r / 10
}

/** «Song (124 BPM, 9A)», same rule as djengine/prep/retempo.py: unchanged parts are left out. */
export function retempoName(stem: string, srcBpm: number, bpm: number, srcCamelot: string | null, semis: number): string {
  const tags: string[] = []
  if (round1(bpm) !== round1(srcBpm)) tags.push(`${round1(bpm)} BPM`)
  if (semis && srcCamelot) tags.push(camelotShift(srcCamelot, semis))
  else if (semis) tags.push(`${semis > 0 ? '+' : ''}${semis}`)
  return tags.length ? `${stem} (${tags.join(', ')})` : `${stem} (copia)`
}

