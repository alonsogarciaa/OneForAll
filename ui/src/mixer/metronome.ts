// Metronome on the song's beat grid: a lookahead scheduler that places short clicks on the audio clock.
import type { Meter } from './mixState'
import type { Segment } from './engine'

const TICK_MS = 25
const WINDOW_S = 0.1
const CLICK_S = 0.03

export interface Clock {
  rate: number
  segments(c0: number, c1: number): Segment[]
}

export function beatsPerBar(meter: Meter): number {
  return { '2/4': 2, '3/4': 3, '4/4': 4, '6/8': 6 }[meter]
}

/** Clicks in [from, to) song seconds. Beat grid from the analysis, else every 60/bpm, else none. */
export function clickTimes(
  beats: number[] | null,
  bpm: number | null,
  from: number,
  to: number,
  meter: Meter,
  offset: number
): { t: number; accent: boolean }[] {
  const bpb = beatsPerBar(meter)
  const accent = (i: number) => (((i - offset) % bpb) + bpb) % bpb === 0
  const out: { t: number; accent: boolean }[] = []
  if (beats && beats.length) {
    beats.forEach((t, i) => {
      if (t >= from && t < to) out.push({ t, accent: accent(i) })
    })
    return out
  }
  if (!bpm) return out
  const step = 60 / bpm
  for (let i = Math.max(0, Math.ceil(from / step - 1e-9)); i * step < to - 1e-12; i++) out.push({ t: i * step, accent: accent(i) })
  return out
}

export class Metronome {
  private timer: ReturnType<typeof setInterval> | null = null
  private scheduledTo = 0
  private opts = { meter: '4/4' as Meter, offset: 0, volume: 0.6 }
  private beats: number[] | null = null
  private bpm: number | null = null
  /** Clicks scheduled but maybe not played yet, so a pause or a seek can take them back. */
  private pending: { osc: OscillatorNode; t: number; countIn: boolean }[] = []

  constructor(private ctx: BaseAudioContext, private clock: Clock, private out: AudioNode = ctx.destination) {}

  start(opts: { meter: Meter; offset: number; volume: number }, beats: number[] | null, bpm: number | null): void {
    const running = this.timer !== null
    this.stop()
    this.opts = opts
    this.beats = beats
    this.bpm = bpm
    // a settings change while running keeps what is already scheduled (no doubled clicks)
    this.scheduledTo = running ? Math.max(this.scheduledTo, this.ctx.currentTime) : this.ctx.currentTime
    this.tick()
    this.timer = setInterval(() => this.tick(), TICK_MS)
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
  }

  /** Pause: no more scheduling, and every click (count-in included) not played yet is cancelled. */
  silence(): void {
    this.stop()
    this.drop(this.ctx.currentTime, true)
  }

  /** The song-to-clock mapping changes at `at` (seek, speed, loop): clicks from then on are scheduled again. */
  resync(at: number): void {
    this.drop(at, false)
    this.scheduledTo = at
    if (this.timer !== null) this.tick()
  }

  private drop(from: number, countIn: boolean): void {
    this.pending = this.pending.filter((p) => {
      if (p.t < from || (p.countIn && !countIn)) return true
      p.osc.stop(p.t) // stopping at its own start time: it never sounds
      return false
    })
  }

  /** Count-in clicks before the audio starts; returns the context time the audio must start at. */
  countIn(bars: number, bpm: number, rate: number, meter: Meter, volume: number): number {
    const interval = 60 / (bpm * rate)
    const bpb = beatsPerBar(meter)
    const start = this.ctx.currentTime + 0.05
    const n = bars * bpb
    for (let i = 0; i < n; i++) this.click(start + i * interval, i % bpb === 0, volume, true)
    return start + n * interval
  }

  private tick(): void {
    const now = this.ctx.currentTime
    this.pending = this.pending.filter((p) => p.t > now - 1) // long played: forget them
    const c0 = Math.max(this.scheduledTo, now)
    const c1 = now + WINDOW_S
    if (c1 <= c0) return
    for (const seg of this.clock.segments(c0, c1)) {
      for (const c of clickTimes(this.beats, this.bpm, seg.song0, seg.song1, this.opts.meter, this.opts.offset)) {
        this.click(seg.ctx0 + (c.t - seg.song0) / this.clock.rate, c.accent, this.opts.volume)
      }
    }
    this.scheduledTo = c1
  }

  private click(t: number, accent: boolean, volume: number, countIn = false): void {
    const osc = this.ctx.createOscillator()
    this.pending.push({ osc, t, countIn })
    const g = this.ctx.createGain()
    osc.frequency.value = accent ? 1500 : 1000
    g.gain.setValueAtTime(Math.max(volume, 0.0001), t)
    g.gain.exponentialRampToValueAtTime(0.0001, t + CLICK_S)
    osc.connect(g)
    g.connect(this.out)
    osc.start(t)
    osc.stop(t + CLICK_S + 0.005)
  }
}
