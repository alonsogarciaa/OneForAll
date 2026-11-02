const MIN_TAPS = 4
const WINDOW = 8 // intervals averaged
const RESET_MS = 2000

/** Tap-along tempo: BPM from the mean of the last 8 intervals, restarting after a 2 s pause. */
export class TapTempo {
  private taps: number[] = []

  constructor(private now: () => number = () => Date.now()) {}

  tap(): number | null {
    const t = this.now()
    const last = this.taps[this.taps.length - 1]
    if (last !== undefined && t - last > RESET_MS) this.taps = []
    this.taps.push(t)
    this.taps = this.taps.slice(-(WINDOW + 1))
    if (this.taps.length < MIN_TAPS) return null
    const span = this.taps[this.taps.length - 1] - this.taps[0]
    const mean = span / (this.taps.length - 1)
    return Math.round((60000 / mean) * 10) / 10
  }

  reset(): void {
    this.taps = []
  }
}
