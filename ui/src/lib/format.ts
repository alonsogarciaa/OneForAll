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
