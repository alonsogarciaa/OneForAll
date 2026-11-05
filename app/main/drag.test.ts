import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { confirmStems, isDraggableStem, normPath } from './drag'

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

describe('confirmStems', () => {
  const engine = { baseUrl: 'http://e', token: 't' }
  it('keeps only files the engine confirms', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ stems: ['a.wav', 'injected.wav'] }), { status: 200 }))
    expect(await confirmStems(['a.wav', 'b.wav'], engine, f as unknown as typeof fetch)).toEqual(['a.wav'])
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('http://e/stems/check')
    expect((init.headers as Record<string, string>)['X-Token']).toBe('t')
  })
  it('allows nothing when the engine is unreachable', async () => {
    const f = vi.fn(async () => { throw new Error('down') })
    expect(await confirmStems(['a.wav'], engine, f as unknown as typeof fetch)).toEqual([])
  })
})
