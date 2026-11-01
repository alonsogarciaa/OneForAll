export type EngineState = 'ready' | 'restarting' | 'failed'

export interface OneForAllBridge {
  getEngine(): Promise<{ baseUrl: string; token: string }>
  restartEngine(): Promise<{ baseUrl: string; token: string }>
  onEngineState(cb: (s: EngineState) => void): () => void
  pathForFile(f: File): string
  pickFolder(): Promise<string | null>
  showInFolder(path: string): void
  openPath(path: string): void
  setTitleBarTheme(dark: boolean): void
}

declare global {
  interface Window {
    oneforall: OneForAllBridge
  }
}
