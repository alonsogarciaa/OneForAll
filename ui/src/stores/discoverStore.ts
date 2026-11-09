import { create } from 'zustand'
import type { MatchResult } from '../lib/types'

export interface QuickInfo {
  bpm: number | null
  camelot: string | null
  failed: boolean
}

export type DiscoverEvent =
  | { type: 'quick.result'; video_id: string; bpm: number | null; camelot: string | null; failed: boolean }
  | { type: 'match.result'; job_id: string; index: number; result: MatchResult }

interface DiscoverState {
  /** Quick analysis per YouTube video id; survives leaving the screen (the engine caches it too). */
  quick: Record<string, QuickInfo>
  /** Matching results per import_match job, by item index. */
  matches: Record<string, Record<number, MatchResult>>
  applyEvent(e: DiscoverEvent): void
  setQuick(entries: Record<string, QuickInfo>): void
  reset(): void
}

export const useDiscoverStore = create<DiscoverState>((set) => ({
  quick: {},
  matches: {},
  applyEvent(e) {
    if (e.type === 'quick.result') {
      set((s) => ({ quick: { ...s.quick, [e.video_id]: { bpm: e.bpm, camelot: e.camelot, failed: e.failed } } }))
    } else if (e.type === 'match.result') {
      set((s) => ({ matches: { ...s.matches, [e.job_id]: { ...(s.matches[e.job_id] ?? {}), [e.index]: e.result } } }))
    }
  },
  setQuick: (entries) => set((s) => ({ quick: { ...s.quick, ...entries } })),
  reset: () => set({ quick: {}, matches: {} })
}))
