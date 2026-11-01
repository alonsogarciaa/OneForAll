import { formatDuration, formatLabel, formatViews } from './format'

describe('format helpers', () => {
  it('formats durations', () => {
    expect(formatDuration(213)).toBe('3:33')
    expect(formatDuration(3725)).toBe('1:02:05')
    expect(formatDuration(5)).toBe('0:05')
  })
  it('formats views Spanish style', () => {
    expect(formatViews(1_200_000)).toBe('1,2 M')
    expect(formatViews(350_000)).toBe('350 K')
    expect(formatViews(999)).toBe('999')
    expect(formatViews(72_000_000)).toBe('72 M')
    expect(formatViews(2_100_000_000)).toBe('2,1 mil M')
  })
  it('labels download options', () => {
    expect(formatLabel({ format: 'mp3', quality: '320' })).toBe('MP3 320')
    expect(formatLabel({ format: 'mp3', quality: 'v0' })).toBe('MP3 V0')
    expect(formatLabel({ format: 'flac', bit_depth: 24 })).toBe('FLAC 24-bit')
    expect(formatLabel({ format: 'aac' })).toBe('AAC')
    expect(formatLabel({ format: 'original' })).toBe('Original')
  })
})
