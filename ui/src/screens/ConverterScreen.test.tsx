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
  name_template: '{artist} - {title}', download_concurrency: 3, tinted: false
}

describe('SettingsScreen', () => {
  function setup() {
    const c = {
      getSettings: vi.fn(async () => settings),
      putSettings: vi.fn(async (s: any) => s),
      updateYtdlp: vi.fn(async () => ({ ok: true, output: 'yt-dlp is up to date' })),
      info: vi.fn(async () => ({ logs_dir: 'C:/data/logs', data_dir: 'C:/data' }))
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
})
