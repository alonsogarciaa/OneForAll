import { FakeCtx } from './fakeAudio'
import { beatsPerBar, clickTimes, Metronome } from './metronome'

describe('clickTimes', () => {
  const beats = [0.5, 1.0, 1.5, 2.0, 2.5]
  it('accents beat 1 of each bar', () => {
    const c = clickTimes(beats, 120, 0, 10, '4/4', 0)
    expect(c.map((x) => x.t)).toEqual(beats)
    expect(c.filter((x) => x.accent).map((x) => x.t)).toEqual([0.5, 2.5])
  })
  it('offset moves the downbeat', () => {
    expect(clickTimes(beats, 120, 0, 10, '4/4', 1).find((x) => x.accent)?.t).toBe(1.0)
  })
  it('window is [from, to)', () => {
    expect(clickTimes(beats, 120, 1.0, 2.0, '4/4', 0).map((x) => x.t)).toEqual([1.0, 1.5])
  })
  it('falls back to a BPM grid, then to nothing', () => {
    expect(clickTimes(null, 120, 0, 1.6, '3/4', 0).map((x) => x.t)).toEqual([0, 0.5, 1.0, 1.5])
    expect(clickTimes([], null, 0, 10, '4/4', 0)).toEqual([])
  })
  it('meters map to beats per bar', () => {
    expect((['2/4', '3/4', '4/4', '6/8'] as const).map((m) => beatsPerBar(m))).toEqual([2, 3, 4, 6])
  })
})

describe('Metronome', () => {
  afterEach(() => vi.useRealTimers())

  it('count-in schedules a bar of clicks at the played tempo and returns when audio starts', () => {
    const ctx = new FakeCtx()
    const m = new Metronome(ctx as unknown as BaseAudioContext, { segments: () => [], rate: 0.5 })
    const start = m.countIn(1, 120, 0.5, '4/4', 0.6)
    const t = ctx.oscs.map((o) => o.startedAt!)
    expect(t).toHaveLength(4)
    expect(t[1] - t[0]).toBeCloseTo(1.0, 6)
    expect(start).toBeCloseTo(t[0] + 4, 6)
    expect(ctx.oscs[0].frequency.value).toBe(1500)
    expect(ctx.oscs[1].frequency.value).toBe(1000)
  })

  it('schedules only the next 100 ms on each 25 ms tick', () => {
    vi.useFakeTimers()
    const ctx = new FakeCtx()
    // song time == ctx time, BPM 1200 = a click every 0.05 s
    const clock = { rate: 1, segments: (c0: number, c1: number) => [{ song0: c0, song1: c1, ctx0: c0 }] }
    const m = new Metronome(ctx as unknown as BaseAudioContext, clock)
    m.start({ meter: '4/4', offset: 0, volume: 0.6 }, null, 1200)
    expect(ctx.oscs.map((o) => o.startedAt)).toEqual([0, 0.05])
    ctx.currentTime = 0.025
    vi.advanceTimersByTime(25)
    expect(ctx.oscs.map((o) => o.startedAt)).toEqual([0, 0.05, 0.1]) // nothing scheduled twice
    m.stop()
    vi.advanceTimersByTime(100)
    expect(ctx.oscs).toHaveLength(3)
  })

  it('changing settings while running does not schedule the same clicks twice', () => {
    vi.useFakeTimers()
    const ctx = new FakeCtx()
    const clock = { rate: 1, segments: (c0: number, c1: number) => [{ song0: c0, song1: c1, ctx0: c0 }] }
    const m = new Metronome(ctx as unknown as BaseAudioContext, clock)
    m.start({ meter: '4/4', offset: 0, volume: 0.6 }, null, 1200)
    m.start({ meter: '4/4', offset: 0, volume: 0.3 }, null, 1200)
    expect(ctx.oscs.map((o) => o.startedAt)).toEqual([0, 0.05])
    m.stop()
  })
})
