import { PeakAccumulator } from './peaks'

describe('PeakAccumulator', () => {
  it('adds per-bucket peaks of every stem and normalises', async () => {
    const acc = new PeakAccumulator(4)
    const a = new Float32Array(8)
    a[2] = -0.5 // bucket 1
    const b = new Float32Array(8)
    b[3] = 0.25 // bucket 1 too
    b[6] = 0.25 // bucket 3
    await acc.add(a)
    await acc.add(b)
    const w = acc.waveform()
    expect(w.peaks).toEqual([0, 1, 0, 1 / 3])
    expect(w.low).toEqual(w.peaks)
  })

  it('yields to the UI while scanning a long stem', async () => {
    const spy = vi.spyOn(globalThis, 'setTimeout')
    const acc = new PeakAccumulator(2000)
    await acc.add(new Float32Array(44100 * 60))
    expect(spy.mock.calls.length).toBeGreaterThan(1)
    spy.mockRestore()
  })
})
