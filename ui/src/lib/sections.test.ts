import { mergeNext, moveBoundary, remove, rename, sectionColor, SECTION_LABELS, splitAt } from './sections'
import type { Section } from './types'

const S = (start: number, end: number, label: Section['label'] = 'Verso'): Section => ({ start, end, label })
const list = [S(0, 15, 'Intro'), S(15, 45, 'Estribillo/Drop'), S(45, 60, 'Outro')]
const bars = Array.from({ length: 40 }, (_, i) => i * 1.875)

describe('section helpers', () => {
  it('labels and colours match the engine', () => {
    expect(SECTION_LABELS).toEqual(['Intro', 'Verso', 'Subida', 'Estribillo/Drop', 'Bajón', 'Outro'])
    expect(sectionColor('Estribillo/Drop')).toBe('rgb(255, 69, 58)')
  })

  it('rename', () => {
    expect(rename(list, 1, 'Bajón')[1].label).toBe('Bajón')
  })

  it('moveBoundary snaps to the nearest bar and moves the previous end too', () => {
    const r = moveBoundary(list, 1, 33.1, bars)
    expect(r[1].start).toBe(33.75)
    expect(r[0].end).toBe(33.75)
    expect(moveBoundary(list, 1, 33.1, null)[1].start).toBe(33.1)
  })

  it('moveBoundary never leaves a section shorter than one bar', () => {
    const r = moveBoundary(list, 1, 44.9, bars)
    expect(r[1].end - r[1].start).toBeGreaterThanOrEqual(1.875 - 1e-9)
    const l = moveBoundary(list, 1, 0.2, bars)
    expect(l[0].end - l[0].start).toBeGreaterThanOrEqual(1.875 - 1e-9)
  })

  it('mergeNext joins a section with the following one', () => {
    expect(mergeNext(list, 0)).toEqual([S(0, 45, 'Intro'), S(45, 60, 'Outro')])
  })

  it('splitAt splits the section under the playhead keeping the label', () => {
    expect(splitAt(list, 30)).toEqual([S(0, 15, 'Intro'), S(15, 30, 'Estribillo/Drop'), S(30, 45, 'Estribillo/Drop'), S(45, 60, 'Outro')])
    expect(splitAt(list, 15)).toEqual(list)
  })

  it('remove: the previous section absorbs it; removing the first extends the next to 0', () => {
    expect(remove(list, 1)).toEqual([S(0, 45, 'Intro'), S(45, 60, 'Outro')])
    expect(remove(list, 0)).toEqual([S(0, 45, 'Estribillo/Drop'), S(45, 60, 'Outro')])
    expect(remove([S(0, 10)], 0)).toEqual([])
  })
})
