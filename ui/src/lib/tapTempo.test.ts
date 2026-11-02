import { TapTempo } from './tapTempo'

function clock() {
  let t = 0
  return { now: () => t, advance: (ms: number) => (t += ms) }
}

describe('TapTempo', () => {
  it('needs 4 taps, then averages the last 8 intervals', () => {
    const c = clock()
    const tt = new TapTempo(c.now)
    expect(tt.tap()).toBeNull()
    c.advance(500); expect(tt.tap()).toBeNull()
    c.advance(500); expect(tt.tap()).toBeNull()
    c.advance(500); expect(tt.tap()).toBe(120)
    for (let i = 0; i < 6; i++) { c.advance(500); tt.tap() }
    c.advance(500)
    expect(tt.tap()).toBe(120)
  })
  it('rounds to one decimal', () => {
    const c = clock()
    const tt = new TapTempo(c.now)
    let bpm: number | null = null
    for (let i = 0; i < 8; i++) { bpm = tt.tap(); c.advance(469) }
    expect(bpm).toBe(127.9)
  })
  it('restarts after a pause longer than 2 s', () => {
    const c = clock()
    const tt = new TapTempo(c.now)
    for (let i = 0; i < 5; i++) { tt.tap(); c.advance(500) }
    c.advance(2500)
    expect(tt.tap()).toBeNull()
  })
})
