import { MixerEngine } from './engine'
import { FakeCtx, RecorderNode, recorderFactory, seconds } from './fakeAudio'
import { defaultState, type MixState } from './mixState'

async function setup(lengths = [10, 10, 10]) {
  const ctx = new FakeCtx()
  const nodes: RecorderNode[] = []
  const eng = new MixerEngine(ctx as unknown as BaseAudioContext, recorderFactory(nodes))
  const names = ['vocals', 'drums', 'bass']
  await eng.load(lengths.map((l, i) => ({ stem: names[i], channels: seconds(l) })))
  return { ctx, nodes, eng }
}
const last = (n: RecorderNode) => n.schedules[n.schedules.length - 1]
const withState = (o: Partial<MixState>): MixState => ({ ...defaultState(), ...o })

describe('MixerEngine', () => {
  it('play schedules every node at the same output and input', async () => {
    const { ctx, nodes, eng } = await setup()
    ctx.currentTime = 3
    eng.play()
    for (const n of nodes) expect(last(n)).toMatchObject({ active: true, output: 3.05, input: 0, rate: 1, semitones: 0 })
  })

  it('play can start at a given context time (after a count-in)', async () => {
    const { nodes, eng } = await setup()
    eng.play(4.2)
    for (const n of nodes) expect(last(n)).toMatchObject({ active: true, output: 4.2 })
  })

  it('solo mutes the others with a 10 ms ramp', async () => {
    const { ctx, eng } = await setup()
    eng.apply(withState({ stems: { drums: { gain: 1, mute: false, solo: true, semis: 0 } } }))
    const [, vocals, drums, bass] = ctx.gains // gains[0] is the master
    expect(drums.gain.calls.at(-1)).toMatchObject({ fn: 'target', v: 1, tc: 0.01 / 3 })
    expect(vocals.gain.value).toBe(0)
    expect(bass.gain.value).toBe(0)
  })

  it('rate change while playing reschedules all nodes at now+0.05 and position follows the rate', async () => {
    const { ctx, nodes, eng } = await setup()
    eng.play()
    ctx.currentTime = 1.05
    expect(eng.position()).toBeCloseTo(1, 5)
    eng.apply(withState({ rate: 0.5 }))
    for (const n of nodes) expect(last(n)).toMatchObject({ output: 1.1, rate: 0.5 })
    expect(last(nodes[0]).input).toBeCloseTo(1.05, 5)
    ctx.currentTime = 3.1
    expect(eng.position()).toBeCloseTo(2.05, 5)
  })

  it('per-stem semitones add to the global key', async () => {
    const { nodes, eng } = await setup()
    eng.play()
    eng.apply(withState({ semis: 2, stems: { vocals: { gain: 1, mute: false, solo: false, semis: -5 } } }))
    expect(last(nodes[0]).semitones).toBe(-3)
    expect(last(nodes[1]).semitones).toBe(2)
  })

  it('loop is clamped to the shortest buffer and position wraps', async () => {
    const { ctx, nodes, eng } = await setup([10, 9.5, 10])
    expect(eng.duration).toBeCloseTo(9.5, 3)
    eng.apply(withState({ loop: { start: 8, end: 12 }, loop_on: true }))
    eng.play()
    for (const n of nodes) expect(last(n)).toMatchObject({ input: 8, loopStart: 8 })
    expect(last(nodes[0]).loopEnd).toBeCloseTo(9.5, 3)
    ctx.currentTime = 0.05 + 2
    expect(eng.position()).toBeCloseTo(8.5, 3)
  })

  it('loop off disables node looping', async () => {
    const { nodes, eng } = await setup()
    eng.play()
    expect(last(nodes[0]).loopStart).toBe(last(nodes[0]).loopEnd)
  })

  it('seek while playing reschedules the input on all nodes; paused seek only moves the position', async () => {
    const { ctx, nodes, eng } = await setup()
    eng.seek(4)
    expect(eng.position()).toBe(4)
    expect(nodes[0].schedules).toHaveLength(0)
    eng.play()
    ctx.currentTime = 1
    eng.seek(6)
    for (const n of nodes) expect(last(n)).toMatchObject({ output: 1.05, input: 6 })
  })

  it('pause keeps the position and stops processing', async () => {
    const { ctx, nodes, eng } = await setup()
    eng.play()
    ctx.currentTime = 2.05
    eng.pause()
    expect(eng.position()).toBeCloseTo(2, 5)
    expect(last(nodes[0])).toMatchObject({ active: false })
    expect(eng.playing).toBe(false)
  })

  it('segments split at the loop wrap', async () => {
    const { eng } = await setup()
    eng.apply(withState({ loop: { start: 2, end: 4 }, loop_on: true }))
    eng.play() // starts at 2 (inside the loop), output 0.05
    const segs = eng.segments(1.55, 2.55)
    expect(segs).toHaveLength(2)
    expect(segs[0].song0).toBeCloseTo(3.5, 5)
    expect(segs[0].song1).toBeCloseTo(4, 5)
    expect(segs[0].ctx0).toBeCloseTo(1.55, 5)
    expect(segs[1].song0).toBe(2)
    expect(segs[1].ctx0).toBeCloseTo(2.05, 5)
  })

  it('dispose stops nodes and closes the context', async () => {
    const { ctx, nodes, eng } = await setup()
    await eng.dispose()
    expect(nodes.every((n) => n.stopped && n.disconnected)).toBe(true)
    expect(ctx.closed).toBe(true)
  })
})
