// Waveform for tracks never analysed: per-bucket peaks added up stem by stem (all bands equal).
import type { AnalysisSidecar } from '../lib/types'

const BUCKETS_PER_SLICE = 100 // then yield, so a 12-minute track never freezes the UI

const yieldToUi = () => new Promise<void>((r) => setTimeout(r, 0))

export class PeakAccumulator {
  private acc: Float32Array

  constructor(buckets = 2000) {
    this.acc = new Float32Array(buckets)
  }

  async add(ch: Float32Array): Promise<void> {
    const n = this.acc.length
    const size = Math.max(1, Math.ceil(ch.length / n))
    for (let b = 0; b < n; b++) {
      let max = 0
      const end = Math.min(ch.length, (b + 1) * size)
      for (let i = b * size; i < end; i++) {
        const v = Math.abs(ch[i])
        if (v > max) max = v
      }
      this.acc[b] += max
      if ((b + 1) % BUCKETS_PER_SLICE === 0) await yieldToUi()
    }
  }

  waveform(): AnalysisSidecar['waveform'] {
    let top = 1e-9
    for (const v of this.acc) top = Math.max(top, v)
    const norm = Array.from(this.acc, (v) => v / top)
    return { peaks: norm, low: norm, mid: norm, high: norm }
  }
}
