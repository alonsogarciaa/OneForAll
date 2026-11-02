import { join, extname, resolve } from 'node:path'
import { existsSync, statSync } from 'node:fs'
import { app, BrowserWindow, dialog, ipcMain, Menu, nativeTheme, shell } from 'electron'
import { EngineProcess, type EngineInfo, type EngineState } from './engineProcess'
import { isDraggableStem, normPath } from './drag'

const AUDIO_EXT = new Set(['.mp3', '.m4a', '.aac', '.wav', '.aif', '.aiff', '.flac', '.ogg', '.opus', '.webm'])
const ROOT = resolve(__dirname, '../..')

function engineOptions() {
  const fake = process.env.ONEFORALL_FAKE === '1'
  const dataRoot = process.env.ONEFORALL_DATA_ROOT
  if (app.isPackaged) {
    const runtime = join(process.resourcesPath, 'runtime')
    return {
      pythonCmd: [join(runtime, 'python', 'python.exe'), '-m', 'djengine'],
      toolsDir: join(runtime, 'bin'),
      modelsDir: join(runtime, 'models'),
      dataRoot,
      fake
    }
  }
  const engineDir = join(ROOT, 'engine')
  const python = process.platform === 'win32' ? join(engineDir, '.venv', 'Scripts', 'python.exe') : join(engineDir, '.venv', 'bin', 'python')
  return {
    pythonCmd: [python, '-m', 'djengine'],
    toolsDir: join(ROOT, 'build', 'runtime', 'bin'),
    cwd: engineDir,
    dataRoot,
    fake
  }
}

const engine = new EngineProcess(engineOptions())
let win: BrowserWindow | null = null
let quitting = false

async function applyTestOverrides(info: EngineInfo): Promise<void> {
  // E2E runs point the music folder somewhere disposable.
  const musicDir = process.env.ONEFORALL_MUSIC_DIR
  if (!musicDir) return
  const h = { 'X-Token': info.token, 'Content-Type': 'application/json' }
  const s = await (await fetch(`${info.baseUrl}/settings`, { headers: h })).json()
  await fetch(`${info.baseUrl}/settings`, { method: 'PUT', headers: h, body: JSON.stringify({ ...s, music_dir: musicDir }) })
}

function createWindow(): void {
  win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 640,
    show: false,
    backgroundMaterial: 'acrylic',
    backgroundColor: '#00000000',
    vibrancy: 'under-window',
    titleBarStyle: 'hidden',
    titleBarOverlay: process.platform === 'win32' ? { color: '#00000000', symbolColor: '#ffffff', height: 44 } : undefined,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })
  win.once('ready-to-show', () => win?.show())
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (e) => e.preventDefault())

  win.on('close', (e) => {
    if (quitting) return
    e.preventDefault()
    void confirmClose()
  })

  if (process.env.ELECTRON_RENDERER_URL) win.loadURL(process.env.ELECTRON_RENDERER_URL)
  else win.loadFile(join(__dirname, '../renderer/index.html'))
}

async function activeCount(): Promise<number> {
  try {
    const info = await engine.current()
    const r = await fetch(`${info.baseUrl}/jobs/active-count`, { headers: { 'X-Token': info.token } })
    return (await r.json()).count ?? 0
  } catch {
    return 0
  }
}

async function confirmClose(): Promise<void> {
  const n = await activeCount()
  if (n > 0 && win) {
    const { response } = await dialog.showMessageBox(win, {
      type: 'warning',
      buttons: ['Cancelar', 'Cerrar y cancelar'],
      defaultId: 0,
      cancelId: 0,
      title: 'OneForAll',
      message: `Hay ${n} procesos en curso (descargas/conversiones). ¿Cerrar y cancelarlos?`
    })
    if (response !== 1) return
  }
  quitting = true
  await engine.stop()
  app.quit()
}

function registerIpc(): void {
  ipcMain.handle('engine:get', () => engine.current())
  ipcMain.handle('engine:restart', () => engine.restart())
  ipcMain.handle('dialog:pickFolder', async () => {
    if (!win) return null
    const r = await dialog.showOpenDialog(win, { properties: ['openDirectory', 'createDirectory'] })
    return r.canceled ? null : r.filePaths[0] ?? null
  })
  ipcMain.on('shell:showInFolder', (_e, p: unknown) => {
    if (typeof p === 'string' && existsSync(p)) shell.showItemInFolder(p)
  })
  ipcMain.on('shell:openPath', (_e, p: unknown) => {
    // Only folders and audio files: never launch arbitrary executables from a renderer request.
    if (typeof p !== 'string' || !existsSync(p)) return
    if (statSync(p).isDirectory() || AUDIO_EXT.has(extname(p).toLowerCase())) void shell.openPath(p)
  })
  const dragAllowed = new Set<string>()
  ipcMain.on('drag:allow', (_e, files: unknown) => {
    if (Array.isArray(files)) for (const f of files) if (typeof f === 'string') dragAllowed.add(normPath(f))
  })
  ipcMain.on('drag:start', (e, file: unknown) => {
    if (typeof file !== 'string' || !isDraggableStem(file, dragAllowed)) return
    const icon = app.isPackaged ? join(process.resourcesPath, 'drag.png') : join(ROOT, 'build', 'resources', 'drag.png')
    e.sender.startDrag({ file, icon })
  })
  ipcMain.on('titlebar:theme', (_e, dark: unknown) => {
    // The acrylic/vibrancy tint follows nativeTheme, so the app theme drives it (not the OS theme).
    nativeTheme.themeSource = dark ? 'dark' : 'light'
    if (process.platform === 'win32' && win) {
      win.setTitleBarOverlay({ color: '#00000000', symbolColor: dark ? '#ffffff' : '#1c1c1e', height: 44 })
    }
  })
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (win) {
      if (win.isMinimized()) win.restore()
      win.focus()
    }
  })
  app.whenReady().then(async () => {
    Menu.setApplicationMenu(null)
    nativeTheme.themeSource = 'dark'
    registerIpc()
    engine.on('state', (s: EngineState) => win?.webContents.send('engine:state', s))
    const ready = engine.start()
    ready.then(applyTestOverrides).catch((e) => console.error('[engine]', e))
    createWindow()
  })
  app.on('window-all-closed', () => app.quit())
  app.on('before-quit', () => {
    quitting = true
  })
}
