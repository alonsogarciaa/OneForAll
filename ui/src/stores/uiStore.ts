import { create } from 'zustand'

export type Route = 'buscar' | 'descargas' | 'biblioteca' | 'armonia' | 'historial' | 'conversor' | 'ajustes'
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
