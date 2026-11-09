import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConverterScreen } from './ConverterScreen'
import { SettingsScreen } from './SettingsScreen'
import { EngineTestProvider } from '../lib/engine'
import { useUiStore } from '../stores/uiStore'

function drop(files: File[]) {
  fireEvent.drop(screen.getByTestId('dropzone'), { dataTransfer: { files, types: ['Files'] } })
}

beforeEach(() => {
  useUiStore.setState({ toasts: [] })
  window.oneforall = {
    pathForFile: (f: File) => `C:/${f.name}`,
    pickFolder: vi.fn(async () => 'D:/Musica'),
    openPath: vi.fn(),
    setTitleBarTheme: vi.fn()
  } as any
})

describe('ConverterScreen', () => {
  it('converts dropped audio files to the chosen format', async () => {
    const c = { convert: vi.fn(async () => ({ jobs: [] })), library: vi.fn(async () => []) } as any
    render(<EngineTestProvider client={c}><ConverterScreen /></EngineTestProvider>)
    drop([new File(['x'], 'a.mp3'), new File(['x'], 'b.wav')])
    expect(screen.getByText('a.mp3')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Formato'), 'flac')
    await userEvent.click(screen.getByRole('button', { name: 'Convertir (2)' }))
    expect(c.convert).toHaveBeenCalledWith(['C:/a.mp3', 'C:/b.wav'], expect.objectContaining({ format: 'flac' }))
  })

  it('rejects files that are not audio', () => {
    const c = { convert: vi.fn(), library: vi.fn(async () => []) } as any
    render(<EngineTestProvider client={c}><ConverterScreen /></EngineTestProvider>)
    drop([new File(['x'], 'x.txt')])
    expect(screen.queryByText('x.txt')).toBeNull()
    expect(useUiStore.getState().toasts.at(-1)?.text).toMatch(/no es un archivo de audio/)
    expect(c.convert).not.toHaveBeenCalled()
  })
})

const settings = {
  music_dir: 'C:/Users/me/Music/OneForAll', default_format: 'mp3', default_quality: '320',
  name_template: '{artist} - {title}', download_concurrency: 3, tinted: false,
  analyze_on_download: true, key_notation: 'camelot', bpm_min: 70, bpm_max: 180,
  stems_dir: null, stems_format: 'wav16', stems_backend: 'auto',
  videos_dir: null, enhance_on_download: false, enhance_mode: 'replace', enhance_format: 'same'
}

describe('SettingsScreen', () => {
  function setup() {
    const c = {
      getSettings: vi.fn(async () => settings),
      putSettings: vi.fn(async (s: any) => s),
      updateYtdlp: vi.fn(async () => ({ ok: true, output: 'yt-dlp is up to date' })),
      info: vi.fn(async () => ({ logs_dir: 'C:/data/logs', data_dir: 'C:/data' })),
      stemsBackend: vi.fn(async () => ({ backend: 'cpu' }))
    } as any
    render(<EngineTestProvider client={c}><SettingsScreen /></EngineTestProvider>)
    return c
  }

  it('toggles tinted mode and saves it', async () => {
    const c = setup()
    await userEvent.click(await screen.findByRole('switch', { name: 'Modo tintado' }))
    expect(document.documentElement.dataset.tinted).toBe('true')
    expect(c.putSettings).toHaveBeenLastCalledWith(expect.objectContaining({ tinted: true }))
  })

  it('previews the file name template live', async () => {
    setup()
    expect(await screen.findByText('Quevedo - La Graciosa.mp3')).toBeInTheDocument()
    const input = screen.getByLabelText('Plantilla de nombre')
    await userEvent.clear(input)
    await userEvent.type(input, '{{title}')
    expect(screen.getByText('La Graciosa.mp3')).toBeInTheDocument()
  })

  it('changes the music folder with the folder picker', async () => {
    const c = setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Cambiar…' }))
    expect(c.putSettings).toHaveBeenLastCalledWith(expect.objectContaining({ music_dir: 'D:/Musica' }))
  })

  it('saves the analysis settings', async () => {
    const c = setup()
    await userEvent.click(await screen.findByRole('switch', { name: 'Analizar al descargar' }))
    expect(c.putSettings).toHaveBeenLastCalledWith(expect.objectContaining({ analyze_on_download: false }))
    await userEvent.click(screen.getByRole('button', { name: 'Musical' }))
    expect(c.putSettings).toHaveBeenLastCalledWith(expect.objectContaining({ key_notation: 'musical' }))
  })

  it('refuses a bpm range where min is not below max', async () => {
    const c = setup()
    const min = await screen.findByLabelText('BPM mínimo')
    const calls = c.putSettings.mock.calls.length
    await userEvent.clear(min)
    await userEvent.type(min, '190')
    expect(screen.getByText('El mínimo debe ser menor que el máximo')).toBeInTheDocument()
    expect(c.putSettings.mock.calls.slice(calls).some((a: any[]) => a[0].bpm_min >= a[0].bpm_max)).toBe(false)
  })

  it('saves stems format and backend', async () => {
    const c = setup()
    await userEvent.selectOptions(await screen.findByLabelText('Formato de los stems'), 'flac')
    expect(c.putSettings).toHaveBeenLastCalledWith(expect.objectContaining({ stems_format: 'flac' }))
    await userEvent.click(screen.getByRole('button', { name: 'Solo CPU' }))
    expect(c.putSettings).toHaveBeenLastCalledWith(expect.objectContaining({ stems_backend: 'cpu' }))
    expect(await screen.findByText('Usando: CPU')).toBeInTheDocument()
  })

  it('enhance on download: the mode and format only show when it is on', async () => {
    const c = setup()
    const sw = await screen.findByRole('switch', { name: 'Mejorar audio al descargar' })
    expect(screen.queryByLabelText('Modo de la mejora')).toBeNull()
    await userEvent.click(sw)
    expect(c.putSettings).toHaveBeenLastCalledWith(expect.objectContaining({ enhance_on_download: true }))
    await userEvent.click(screen.getByRole('button', { name: 'Copia nueva' }))
    expect(c.putSettings).toHaveBeenLastCalledWith(expect.objectContaining({ enhance_mode: 'copy' }))
    await userEvent.click(screen.getByRole('button', { name: 'FLAC' }))
    expect(c.putSettings).toHaveBeenLastCalledWith(expect.objectContaining({ enhance_format: 'flac' }))
  })

  it('videos folder and the Apollo credit', async () => {
    const c = setup()
    expect(await screen.findByText('C:/Users/me/Music/OneForAll/Videos')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Cambiar carpeta de vídeos' }))
    expect(c.putSettings).toHaveBeenLastCalledWith(expect.objectContaining({ videos_dir: 'D:/Musica' }))
    expect(screen.getByText(/Apollo \(Kai Li y Yi Luo\), con licencia CC BY-SA 4\.0/)).toBeInTheDocument()
  })
})
