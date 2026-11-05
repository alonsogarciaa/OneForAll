export const STEM_IDS = ['vocals', 'drums', 'bass', 'guitar', 'piano', 'other'] as const
export type StemId = (typeof STEM_IDS)[number]

export const STEM_LABEL: Record<string, string> = {
  vocals: 'Voz',
  drums: 'Batería',
  bass: 'Bajo',
  guitar: 'Guitarra',
  piano: 'Piano',
  other: 'Resto',
  lead_vocals: 'Voz principal',
  backing_vocals: 'Coros'
}

export const DEFAULT_STEMS: StemId[] = ['vocals', 'drums', 'bass', 'guitar']

/** Seconds of work per second of audio: mean of recent separations, else 0.4 (Ryzen 5 5600X, CPU). */
export function estimateSeconds(durationS: number, history: number[] = []): number {
  const recent = history.slice(-5)
  const rate = recent.length ? recent.reduce((a, b) => a + b, 0) / recent.length : 0.4
  return Math.round(durationS * rate)
}

export function estimateLabel(seconds: number): string {
  return seconds < 60 ? '≈ menos de 1 min en este equipo' : `≈ ${Math.ceil(seconds / 60)} min en este equipo`
}
