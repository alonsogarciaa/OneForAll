import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { isDraggableStem, normPath } from './drag'

describe('isDraggableStem', () => {
  const dir = mkdtempSync(join(tmpdir(), 'drag-'))
  const wav = join(dir, 'vocals.wav')
  const exe = join(dir, 'evil.exe')
  writeFileSync(wav, 'x')
  writeFileSync(exe, 'x')
  const allowed = new Set([normPath(wav), normPath(exe)])

  it('accepts an allowed existing audio file', () => {
    expect(isDraggableStem(wav, allowed)).toBe(true)
  })
  it('accepts the same file reached through ..', () => {
    expect(isDraggableStem(join(dir, 'x', '..', 'vocals.wav'), allowed)).toBe(true)
  })
  it('refuses files that were not allowed, non-audio and missing files', () => {
    expect(isDraggableStem(join(dir, 'other.wav'), allowed)).toBe(false)
    expect(isDraggableStem(exe, allowed)).toBe(false)
    expect(isDraggableStem(join(dir, 'gone.wav'), new Set([normPath(join(dir, 'gone.wav'))]))).toBe(false)
  })
})
