import { existsSync, statSync } from 'node:fs'
import { extname, resolve } from 'node:path'

const AUDIO = new Set(['.wav', '.flac', '.mp3', '.aiff', '.aif', '.m4a', '.ogg', '.opus'])

export function normPath(p: string): string {
  const r = resolve(p)
  return process.platform === 'win32' ? r.toLowerCase() : r
}

/** Ask the engine which of these files are its stems: the renderer alone cannot widen the allow-list. */
export async function confirmStems(
  files: string[],
  engine: { baseUrl: string; token: string },
  fetchFn: typeof fetch = fetch
): Promise<string[]> {
  try {
    const r = await fetchFn(`${engine.baseUrl}/stems/check`, {
      method: 'POST',
      headers: { 'X-Token': engine.token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ files: files.slice(0, 64) })
    })
    if (!r.ok) return []
    const body = (await r.json()) as { stems?: unknown }
    return Array.isArray(body.stems) ? body.stems.filter((f): f is string => typeof f === 'string' && files.includes(f)) : []
  } catch {
    return []
  }
}

/** Only stems the renderer got from the engine may be dragged out of the app. */
export function isDraggableStem(file: string, allowed: Set<string>): boolean {
  const n = normPath(file)
  if (!allowed.has(n) || !AUDIO.has(extname(n))) return false
  return existsSync(n) && statSync(n).isFile()
}
