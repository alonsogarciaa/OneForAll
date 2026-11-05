import { contextBridge, ipcRenderer, webUtils } from 'electron'

type EngineState = 'ready' | 'restarting' | 'failed'

contextBridge.exposeInMainWorld('oneforall', {
  getEngine: (): Promise<{ baseUrl: string; token: string }> => ipcRenderer.invoke('engine:get'),
  restartEngine: (): Promise<{ baseUrl: string; token: string }> => ipcRenderer.invoke('engine:restart'),
  onEngineState: (cb: (s: EngineState) => void): (() => void) => {
    const listener = (_e: unknown, s: EngineState) => cb(s)
    ipcRenderer.on('engine:state', listener)
    return () => ipcRenderer.removeListener('engine:state', listener)
  },
  pathForFile: (f: File): string => webUtils.getPathForFile(f),
  pickFolder: (): Promise<string | null> => ipcRenderer.invoke('dialog:pickFolder'),
  showInFolder: (path: string): void => ipcRenderer.send('shell:showInFolder', path),
  openPath: (path: string): void => ipcRenderer.send('shell:openPath', path),
  setTitleBarTheme: (dark: boolean): void => ipcRenderer.send('titlebar:theme', dark),
  allowDrag: (files: string[]): void => ipcRenderer.send('drag:allow', files),
  startDrag: (file: string): void => ipcRenderer.send('drag:start', file)
})
