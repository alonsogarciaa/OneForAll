import { audible, defaultState, effectiveSemis, mixerStems, parseState } from './mixState'

describe('mixState', () => {
  it('defaults match the engine model', () => {
    const s = defaultState()
    expect(s).toMatchObject({ version: 1, rate: 1, semis: 0, master: 1, loop: null, loop_on: false })
    expect(s.metronome).toEqual({ on: false, volume: 0.6, count_in: 1, meter: '4/4', offset: 0 })
  })

  it('drops invalid fields to their defaults and clamps numbers', () => {
    expect(parseState({ rate: 3 }).rate).toBe(1)
    expect(parseState(null)).toEqual(defaultState())
    expect(parseState({ semis: 30 }).semis).toBe(12)
    expect(parseState({ stems: { kazoo: { gain: 1 }, drums: { gain: 9 } } }).stems).toEqual({ drums: { gain: 1.5, mute: false, solo: false, semis: 0 } })
    expect(parseState({ loop: { start: 5, end: 2 } }).loop).toBeNull()
    expect(parseState({ metronome: { meter: '7/8' } }).metronome.meter).toBe('4/4')
  })

  it('effective semitones add up and clamp', () => {
    const s = { ...defaultState(), semis: 10, stems: { vocals: { gain: 1, mute: false, solo: false, semis: 5 } } }
    expect(effectiveSemis(s, 'vocals')).toBe(12)
    expect(effectiveSemis(s, 'drums')).toBe(10)
  })

  it('solo wins over mute', () => {
    const names = ['vocals', 'drums', 'bass']
    const st = (o: object) => ({ gain: 1, mute: false, solo: false, semis: 0, ...o })
    expect(audible({ ...defaultState(), stems: { drums: st({ solo: true }) } }, names)).toEqual(['drums'])
    expect(audible({ ...defaultState(), stems: { vocals: st({ mute: true }) } }, names)).toEqual(['drums', 'bass'])
  })

  it('karaoke stems replace vocals and keep the mixer order', () => {
    const list = ['other', 'drums', 'vocals', 'backing_vocals', 'lead_vocals'].map((stem) => ({ stem, file: `${stem}.wav` }))
    expect(mixerStems(list).map((s) => s.stem)).toEqual(['lead_vocals', 'backing_vocals', 'drums', 'other'])
    expect(mixerStems([{ stem: 'vocals', file: 'v' }, { stem: 'lead_vocals', file: 'l' }]).map((s) => s.stem)).toEqual(['vocals', 'lead_vocals'])
  })
})
