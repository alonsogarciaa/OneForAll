import { test, expect, _electron as electron, type ElectronApplication, type Page } from '@playwright/test'
import { mkdtempSync, readdirSync, existsSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { execFileSync } from 'node:child_process'
import { join } from 'node:path'

let app: ElectronApplication
let page: Page
let dataRoot: string
let musicDir: string

async function launch(fakeDelay = '1') {
  const root = mkdtempSync(join(tmpdir(), 'oneforall-e2e-'))
  dataRoot = join(root, 'data')
  musicDir = join(root, 'music')
  app = await electron.launch({
    args: ['.'],
    env: { ...process.env, ONEFORALL_FAKE: '1', ONEFORALL_FAKE_DELAY: fakeDelay, ONEFORALL_DATA_ROOT: dataRoot, ONEFORALL_MUSIC_DIR: musicDir }
  })
  page = await app.firstWindow()
  await page.waitForSelector('.app-shell')
  await expect(page.getByText('Arrancando el motor…')).toHaveCount(0, { timeout: 30_000 })
}

test.afterEach(async () => {
  if (!app) return
  // Electron's helper processes keep the stdio pipes open on Windows, so kill the whole tree.
  const pid = app.process().pid
  if (pid) {
    try {
      execFileSync('taskkill', ['/pid', String(pid), '/T', '/F'], { stdio: 'ignore' })
    } catch {
      // already gone
    }
  }
})

async function search(q: string) {
  await page.fill('input[aria-label="Buscar en YouTube Music"]', q)
  await page.keyboard.press('Enter')
  await page.waitForSelector('[data-row]')
}

function downloadFirstSong() {
  return page.locator('[data-row]').first().getByRole('button', { name: /Descargar en/ }).click()
}

const nav = (name: string) => page.locator('.nav-item', { hasText: name }).click()
const musicFiles = () => (existsSync(musicDir) ? readdirSync(musicDir) : [])
const tmpEntries = () => readdirSync(join(dataRoot, 'tmp'))

test('search → download → library', async () => {
  await launch()
  await search('graciosa')
  await downloadFirstSong()
  await nav('Descargas')
  await expect(page.getByRole('button', { name: 'Mostrar en carpeta' })).toBeVisible({ timeout: 30_000 })
  expect(musicFiles()).toContain('Fake Artist - La Graciosa.mp3')
  await nav('Biblioteca')
  await expect(page.getByText('La Graciosa')).toBeVisible()
})

test('duplicate → force → (1) in the same folder', async () => {
  await launch()
  await search('graciosa')
  await downloadFirstSong()
  await expect.poll(musicFiles, { timeout: 30_000 }).toContain('Fake Artist - La Graciosa.mp3')
  await downloadFirstSong()
  await expect(page.getByText('Ya tienes esta canción')).toBeVisible()
  await page.getByRole('button', { name: 'Descargar igualmente' }).click()
  await expect.poll(musicFiles, { timeout: 30_000 }).toContain('Fake Artist - La Graciosa (1).mp3')
  expect(musicFiles().filter((f) => statSync(join(musicDir, f)).isDirectory())).toEqual([])
})

test('cancel leaves nothing behind', async () => {
  await launch('8')
  await search('graciosa')
  await downloadFirstSong()
  await nav('Descargas')
  await page.getByRole('button', { name: 'Cancelar' }).first().click()
  await expect(page.getByText('Cancelado')).toBeVisible({ timeout: 15_000 })
  expect(musicFiles()).toEqual([])
  await expect.poll(tmpEntries, { timeout: 10_000 }).toEqual([])
})

test('playlist summary reports the failed track', async () => {
  await launch()
  await search('x')
  await page.getByRole('button', { name: 'Playlists' }).click()
  await page.locator('[data-row]').first().click()
  await page.getByRole('button', { name: /Descargar playlist \(3\)/ }).click()
  await expect(page.getByText('2 descargadas · 1 fallidas · 0 ya en tu biblioteca')).toBeVisible({ timeout: 45_000 })
})

test('closing with active jobs asks first', async () => {
  await launch('20')
  await search('graciosa')
  await downloadFirstSong()
  await expect(page.locator('.mini-queue')).toBeVisible()
  await app.evaluate(({ dialog }) => {
    ;(globalThis as any).__closeMessage = null
    dialog.showMessageBox = (async (_w: unknown, opts: { message: string }) => {
      ;(globalThis as any).__closeMessage = opts.message
      return { response: 0, checkboxChecked: false }
    }) as any
  })
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].close())
  await expect.poll(() => app.evaluate(() => (globalThis as any).__closeMessage), { timeout: 10_000 }).toContain('procesos en curso')
  // "Cancelar" keeps the window open
  expect(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length)).toBe(1)
})

test('download → automatic analysis → data sheet → tap tempo → harmony', async () => {
  await launch()
  await search('graciosa')
  await downloadFirstSong()
  await nav('Biblioteca')
  const row = page.locator('.stable-row:not(.stable-head)').first()
  await expect(row.locator('.key-chip')).toBeVisible({ timeout: 90_000 })
  await expect(row).toContainText(/\d+\.\d/)
  await row.dblclick()
  await expect(page.locator('canvas.waveform')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('.ds-label', { hasText: 'BPM' })).toBeVisible()
  await page.locator('.ds-value').first().click() // focus inside the sheet, not on a button
  await page.clock.install() // exact 500 ms between taps, independent of automation latency
  await page.clock.pauseAt(new Date(Date.now() + 1000))
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Space')
    await page.clock.runFor(500)
  }
  await expect(page.locator('.tap-bpm')).toHaveText('120.0')
  await page.clock.resume() // timers (search debounce) need real time again
  await page.keyboard.press('Escape')
  await nav('Armonía')
  await page.selectOption('select[aria-label="Pista de referencia"]', { index: 1 })
  await expect(page.getByText('No hay pistas compatibles con estos criterios')).toBeVisible()
})
