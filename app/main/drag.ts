import { existsSync, statSync } from 'node:fs'
import { extname, resolve } from 'node:path'

const AUDIO = new Set(['.wav', '.flac', '.mp3', '.aiff', '.aif', '.m4a', '.ogg', '.opus'])

export function normPath(p: string): string {
  const r = resolve(p)
  return process.platform === 'win32' ? r.toLowerCase() : r
}

/** Only stems the renderer got from the engine may be dragged out of the app. */
export function isDraggableStem(file: string, allowed: Set<string>): boolean {
  const n = normPath(file)
  if (!allowed.has(n) || !AUDIO.has(extname(n))) return false
  return existsSync(n) && statSync(n).isFile()
}
