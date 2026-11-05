// Real-time stem player: one stretch node per stem on one audio clock. Every change is scheduled
// at the same context time on every node, so the stems never drift apart.
import { audible, defaultState, effectiveSemis, stemState, type MixState } from './mixState'
import type { CreateStretch, StretchNode, StretchSchedule } from './stretch'

const LEAD = 0.05 // seconds ahead: lets each node compensate its own latency
const RAMP = 0.01 / 3 // setTargetAtTime constant: ~10 ms gain ramps, no clicks

export interface Segment {
  song0: number // song seconds at ctx0
  song1: number
  ctx0: number
}

interface Strip {
  stem: string
  node: StretchNode
  gain: GainNode
}

export class MixerEngine {
  playing = false
  duration = 0
  private strips: Strip[] = []
  private master: GainNode
  private state: MixState = defaultState()
  private pausedAt = 0
  private ctxT0 = 0
  private songT0 = 0

  constructor(private ctx: BaseAudioContext, private createStretch: CreateStretch) {
    this.master = ctx.createGain()
    this.master.connect(ctx.destination)
  }

  get rate(): number {
    return this.state.rate
  }

  async load(stems: { stem: string; channels: Float32Array[] }[], onProgress?: (n: number) => void): Promise<void> {
    let shortest = Infinity
    for (const [i, s] of stems.entries()) {
      const node = await this.createStretch(this.ctx)
      const gain = this.ctx.createGain()
      node.connect(gain)
      gain.connect(this.master)
      await node.addBuffers(s.channels)
      shortest = Math.min(shortest, s.channels[0].length / this.ctx.sampleRate)
      this.strips.push({ stem: s.stem, node, gain })
      onProgress?.(i + 1)
    }
    this.duration = Number.isFinite(shortest) ? shortest : 0
  }

  apply(next: MixState): void {
    const prev = this.state
    const now = this.ctx.currentTime
    const input = this.playing ? this.songAt(now + LEAD) : 0 // with the old rate and loop
    this.state = next
    const on = audible(next, this.strips.map((s) => s.stem))
    for (const s of this.strips) s.gain.gain.setTargetAtTime(on.includes(s.stem) ? stemState(next, s.stem).gain : 0, now, RAMP)
    this.master.gain.setTargetAtTime(next.master, now, RAMP)
    if (!this.playing) return
    const moved =
      prev.rate !== next.rate ||
      this.strips.some((s) => effectiveSemis(prev, s.stem) !== effectiveSemis(next, s.stem)) ||
      JSON.stringify(this.loopRange(prev)) !== JSON.stringify(this.loopRange(next))
    if (moved) this.reschedule(input, now + LEAD)
  }

  play(): void {
    if (this.playing) return
    const loop = this.loopRange(this.state)
    let input = this.pausedAt
    if (loop && (input < loop[0] || input >= loop[1])) input = loop[0]
    this.playing = true
    this.reschedule(input, this.ctx.currentTime + LEAD, true)
  }

  pause(): void {
    if (!this.playing) return
    const now = this.ctx.currentTime
    this.pausedAt = this.songAt(now)
    this.playing = false
    for (const s of this.strips) s.node.schedule({ output: now, active: false })
  }

  seek(t: number): void {
    const to = Math.max(0, Math.min(this.duration, t))
    if (!this.playing) {
      this.pausedAt = to
      return
    }
    this.reschedule(to, this.ctx.currentTime + LEAD)
  }

  position(): number {
    return this.playing ? this.songAt(this.ctx.currentTime) : this.pausedAt
  }

  /** Song-time pieces of a context-time window, split where the loop wraps (for the metronome). */
  segments(c0: number, c1: number): Segment[] {
    if (!this.playing) return []
    const out: Segment[] = []
    const loop = this.loopRange(this.state)
    const rate = this.state.rate
    let c = Math.max(c0, this.ctxT0)
    let s = this.songAt(c)
    while (c < c1) {
      if (loop && s < loop[1]) {
        const wrapAt = c + (loop[1] - s) / rate
        if (wrapAt < c1) {
          out.push({ song0: s, song1: loop[1], ctx0: c })
          c = wrapAt
          s = loop[0]
          continue
        }
      }
      out.push({ song0: s, song1: s + (c1 - c) * rate, ctx0: c })
      break
    }
    return out
  }

  async dispose(): Promise<void> {
    this.playing = false
    for (const s of this.strips) {
      s.node.stop()
      s.node.disconnect()
      s.gain.disconnect()
    }
    this.strips = []
    this.master.disconnect()
    await (this.ctx as AudioContext).close?.()
  }

  private loopRange(st: MixState): [number, number] | null {
    if (!st.loop_on || !st.loop) return null
    const end = Math.min(st.loop.end, this.duration)
    return end > st.loop.start ? [st.loop.start, end] : null
  }

  private songAt(c: number): number {
    const raw = c <= this.ctxT0 ? this.songT0 : this.songT0 + (c - this.ctxT0) * this.state.rate
    const loop = this.loopRange(this.state)
    if (loop && this.songT0 < loop[1] && raw >= loop[1]) return loop[0] + ((raw - loop[0]) % (loop[1] - loop[0]))
    return Math.min(raw, this.duration)
  }

  private reschedule(input: number, output: number, start = false): void {
    this.songT0 = input
    this.ctxT0 = output
    const loop = this.loopRange(this.state)
    for (const s of this.strips) {
      const o: StretchSchedule = {
        output,
        input,
        rate: this.state.rate,
        semitones: effectiveSemis(this.state, s.stem),
        loopStart: loop ? loop[0] : 0,
        loopEnd: loop ? loop[1] : 0
      }
      if (start) o.active = true
      s.node.schedule(o)
    }
  }
}
