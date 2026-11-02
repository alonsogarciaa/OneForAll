// Camelot wheel helpers. Same table as the engine (djengine/analysis/camelot.py).

const NAMES: Record<string, string> = {
  '1A': 'Sol#m', '2A': 'Re#m', '3A': 'La#m', '4A': 'Fam', '5A': 'Dom', '6A': 'Solm',
  '7A': 'Rem', '8A': 'Lam', '9A': 'Mim', '10A': 'Sim', '11A': 'Fa#m', '12A': 'Do#m',
  '1B': 'Si', '2B': 'Fa#', '3B': 'Do#', '4B': 'Sol#', '5B': 'Re#', '6B': 'La#',
  '7B': 'Fa', '8B': 'Do', '9B': 'Sol', '10B': 'Re', '11B': 'La', '12B': 'Mi'
}

export const CAMELOT_CODES = Object.keys(NAMES)
export type CompatLevel = 'same' | 'adjacent' | 'relative'

export function displayKey(code: string | null | undefined): string {
  if (!code || !NAMES[code]) return '—'
  return `${code} · ${NAMES[code]}`
}

/** One hue per wheel position (1 → 0°, 30° steps); minor keys a touch darker than major. */
export function camelotColor(code: string): string {
  const n = parseInt(code, 10)
  const hue = ((n - 1) * 30) % 360
  // yellows and greens are bright: darken them so white text keeps 4.5:1
  const light = hue >= 30 && hue <= 180 ? 27 : 38
  const l = code.endsWith('A') ? light - 3 : light
  return hslToHex(hue, 72, l)
}

export function compatLabel(level: CompatLevel): string {
  return { same: 'Misma clave', adjacent: '±1', relative: 'Relativa' }[level]
}

function hslToHex(h: number, s: number, l: number): string {
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100)
  const f = (n: number) => {
    const k = (n + h / 30) % 12
    const c = l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))
    return Math.round(255 * c).toString(16).padStart(2, '0')
  }
  return `#${f(0)}${f(8)}${f(4)}`
}

function luminance(hex: string): number {
  const v = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  const [r, g, b] = v.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrastRatio(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}
