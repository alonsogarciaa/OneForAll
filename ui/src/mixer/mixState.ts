// Mixer state: same shape and ranges as the engine model (djengine/mixer/state.py).

export type Meter = '2/4' | '3/4' | '4/4' | '6/8'
export interface StemState { gain: number; mute: boolean; solo: boolean; semis: number }
export interface Loop { start: number; end: number }
export interface MetronomeState { on: boolean; volume: number; count_in: 0 | 1 | 2; meter: Meter; offset: number }
export interface MixState {
  version: 1
  rate: number
  semis: number
  master: number
  stems: Record<string, StemState>
  loop: Loop | null
  loop_on: boolean
  metronome: MetronomeState
}

/** Longest track the mixer opens (all stems live in memory). */
export const MIXER_MAX_SECONDS = 12 * 60

export const MIXER_ORDER = ['vocals', 'lead_vocals', 'backing_vocals', 'drums', 'bass', 'guitar', 'piano', 'other']
export const METERS: Meter[] = ['2/4', '3/4', '4/4', '6/8']
const DEFAULT_STEM: StemState = { gain: 1, mute: false, solo: false, semis: 0 }

export function defaultState(): MixState {
  return {
    version: 1, rate: 1, semis: 0, master: 1, stems: {}, loop: null, loop_on: false,
    metronome: { on: false, volume: 0.6, count_in: 1, meter: '4/4', offset: 0 }
  }
}

const num = (v: unknown, lo: number, hi: number, dflt: number) =>
  typeof v === 'number' && Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : dflt
const int = (v: unknown, lo: number, hi: number, dflt: number) => Math.round(num(v, lo, hi, dflt))
const bool = (v: unknown, dflt: boolean) => (typeof v === 'boolean' ? v : dflt)

export function stemState(s: MixState, stem: string): StemState {
  return s.stems[stem] ?? DEFAULT_STEM
}

/** Anything from storage or the engine: invalid fields fall back to defaults, numbers are clamped. */
export function parseState(x: unknown): MixState {
  const d = defaultState()
  if (!x || typeof x !== 'object') return d
  const o = x as Record<string, any>
  const stems: Record<string, StemState> = {}
  if (o.stems && typeof o.stems === 'object') {
    for (const [k, v] of Object.entries(o.stems as Record<string, any>)) {
      if (!MIXER_ORDER.includes(k) || !v || typeof v !== 'object') continue
      stems[k] = { gain: num(v.gain, 0, 1.5, 1), mute: bool(v.mute, false), solo: bool(v.solo, false), semis: int(v.semis, -12, 12, 0) }
    }
  }
  const l = o.loop
  const loop = l && typeof l.start === 'number' && typeof l.end === 'number' && l.start >= 0 && l.end > l.start ? { start: l.start, end: l.end } : null
  const m = (o.metronome && typeof o.metronome === 'object' ? o.metronome : {}) as Record<string, any>
  return {
    version: 1,
    rate: o.rate === undefined ? d.rate : typeof o.rate === 'number' && o.rate >= 0.5 && o.rate <= 1 ? Math.round(o.rate * 100) / 100 : d.rate,
    semis: int(o.semis, -12, 12, 0),
    master: num(o.master, 0, 1.5, 1),
    stems,
    loop,
    loop_on: loop ? bool(o.loop_on, false) : false,
    metronome: {
      on: bool(m.on, false),
      volume: num(m.volume, 0, 1, 0.6),
      count_in: [0, 1, 2].includes(m.count_in) ? m.count_in : 1,
      meter: METERS.includes(m.meter) ? m.meter : '4/4',
      offset: int(m.offset, -7, 7, 0)
    }
  }
}

export function effectiveSemis(s: MixState, stem: string): number {
  return Math.max(-12, Math.min(12, s.semis + stemState(s, stem).semis))
}

/** Solo wins: if any stem is solo only those sound; otherwise every non-muted stem. */
export function audible(s: MixState, names: string[]): string[] {
  if (names.some((n) => stemState(s, n).solo)) return names.filter((n) => stemState(s, n).solo)
  return names.filter((n) => !stemState(s, n).mute)
}

/** Stems the mixer loads: lead + backing replace vocals (so the voice is not heard twice), in mixer order. */
export function mixerStems<T extends { stem: string }>(list: T[]): T[] {
  const has = (s: string) => list.some((x) => x.stem === s)
  const karaoke = has('lead_vocals') && has('backing_vocals')
  return list
    .filter((x) => MIXER_ORDER.includes(x.stem) && !(karaoke && x.stem === 'vocals'))
    .sort((a, b) => MIXER_ORDER.indexOf(a.stem) - MIXER_ORDER.indexOf(b.stem))
}
