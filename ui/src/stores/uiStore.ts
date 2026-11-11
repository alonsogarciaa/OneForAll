import { create } from 'zustand'

export type Route = 'buscar' | 'descubrir' | 'descargas' | 'biblioteca' | 'armonia' | 'historial' | 'conversor' | 'ajustes'
export type ToastKind = 'info' | 'error' | 'success'

export interface Toast {
  id: number
  kind: ToastKind
  text: string
}

interface UiState {
  route: Route
  toasts: Toast[]
  tinted: boolean
  theme: 'dark' | 'light'
  /** Text in the top search pill, and the last query submitted from it. */
  query: string
  submittedQuery: string
  setQuery(q: string): void
  submitQuery(q: string): void
  /** File shown in the data sheet (waveform, BPM, key, tap tempo), or null. */
  dataSheet: string | null
  openData(path: string): void
  closeData(): void
  /** Files waiting for the "Separar stems" sheet, with their total duration. */
  stemsFor: { paths: string[]; durationS: number | null } | null
  openStems(paths: string[], durationS?: number | null): void
  closeStems(): void
  /** Track open in the practice mixer (it replaces the data sheet, which comes back on close). */
  mixerFor: string | null
  openMixer(path: string): void
  closeMixer(): void
  /** File open in the "Cambiar BPM y tono" sheet. */
  retempoFor: string | null
  openRetempo(path: string): void
  closeRetempo(): void
  /** Library track whose similar songs the Descubrir screen shows. */
  discoverSeed: number | null
  openDiscover(trackId: number): void
  /** List read from a pasted Spotify / Apple Music / SoundCloud link. */
  importList: import('../lib/types').ImportList | null
  openImport(list: import('../lib/types').ImportList): void
  closeImport(): void
  /** Tracks waiting for the "Mejorar audio" sheet. */
  enhanceFor: { path: string; enhanced: boolean }[] | null
  openEnhance(items: { path: string; enhanced: boolean }[]): void
  closeEnhance(): void
  /** "Exportar vídeo…" sheet: selected track ids. */
  videoExport: { trackIds: number[] } | null
  openVideoExport(trackIds: number[]): void
  closeVideoExport(): void
  /** "Exportar a…" sheet: selected track ids, or null for the whole library. */
  djExport: { trackIds: number[] | null } | null
  openDjExport(trackIds: number[] | null): void
  closeDjExport(): void
  navigate(r: Route): void
  toast(text: string, kind?: ToastKind): void
  dismissToast(id: number): void
  setTinted(v: boolean): void
  setTheme(t: 'dark' | 'light'): void
}

const THEME_KEY = 'oneforall.theme'

function savedTheme(): 'dark' | 'light' {
  try {
    return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

let nextId = 1
const TOAST_MS = 4500

export const useUiStore = create<UiState>((set, get) => ({
  route: 'buscar',
  toasts: [],
  tinted: false,
  theme: savedTheme(),
  query: '',
  submittedQuery: '',
  setQuery: (query) => set({ query }),
  submitQuery: (q) => set({ query: q, submittedQuery: q.trim(), route: 'buscar' }),
  dataSheet: null,
  openData: (dataSheet) => set({ dataSheet }),
  closeData: () => set({ dataSheet: null }),
  stemsFor: null,
  openStems: (paths, durationS = null) => set({ stemsFor: { paths, durationS } }),
  closeStems: () => set({ stemsFor: null }),
  mixerFor: null,
  openMixer: (path) => set({ mixerFor: path, dataSheet: null }),
  closeMixer: () => set((s) => ({ mixerFor: null, dataSheet: s.mixerFor })),
  retempoFor: null,
  openRetempo: (path) => set({ retempoFor: path }),
  closeRetempo: () => set({ retempoFor: null }),
  discoverSeed: null,
  openDiscover: (trackId) => set({ discoverSeed: trackId, route: 'descubrir', dataSheet: null }),
  importList: null,
  openImport: (list) => set({ importList: list }),
  closeImport: () => set({ importList: null }),
  enhanceFor: null,
  openEnhance: (items) => set({ enhanceFor: items }),
  closeEnhance: () => set({ enhanceFor: null }),
  videoExport: null,
  openVideoExport: (trackIds) => set({ videoExport: { trackIds } }),
  closeVideoExport: () => set({ videoExport: null }),
  djExport: null,
  openDjExport: (trackIds) => set({ djExport: { trackIds } }),
  closeDjExport: () => set({ djExport: null }),
  navigate: (route) => set({ route }),
  toast(text, kind = 'info') {
    const id = nextId++
    set((s) => ({ toasts: [...s.toasts.slice(-3), { id, kind, text }] }))
    setTimeout(() => get().dismissToast(id), TOAST_MS)
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  setTinted(tinted) {
    document.documentElement.dataset.tinted = String(tinted)
    set({ tinted })
  },
  setTheme(theme) {
    document.documentElement.dataset.theme = theme
    window.oneforall?.setTitleBarTheme(theme === 'dark')
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      // storage unavailable: theme just won't persist
    }
    set({ theme })
  }
}))
