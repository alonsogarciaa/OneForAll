import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HistoryScreen } from './HistoryScreen'
import { LibraryScreen } from './LibraryScreen'
import { EngineTestProvider } from '../lib/engine'
import type { HistoryEntry, TrackRecord } from '../lib/types'

const entry = (id: number, title: string): HistoryEntry => ({
  id, track_id: null, video_id: 'v', title, artist: 'Quevedo', action: 'download', status: 'done', at: '2026-11-01T10:00:00+00:00'
})

function historyClient() {
  return {
    history: vi.fn(async () => [entry(1, 'Uno'), entry(2, 'Dos'), entry(3, 'Tres')]),
    deleteHistory: vi.fn(async () => ({ deleted: 1 }))
  } as any
}

describe('HistoryScreen', () => {
  it('deletes only the selected rows', async () => {
    const c = historyClient()
    render(<EngineTestProvider client={c}><HistoryScreen /></EngineTestProvider>)
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Seleccionar Uno' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar Tres' }))
    await userEvent.click(screen.getByRole('button', { name: 'Borrar seleccionadas (2)' }))
    expect(c.deleteHistory).toHaveBeenCalledWith([1, 3])
  })

  it('disables selective delete with nothing selected', async () => {
    render(<EngineTestProvider client={historyClient()}><HistoryScreen /></EngineTestProvider>)
    expect(await screen.findByRole('button', { name: 'Borrar seleccionadas (0)' })).toBeDisabled()
  })

  it('asks before deleting everything', async () => {
    const c = historyClient()
    render(<EngineTestProvider client={c}><HistoryScreen /></EngineTestProvider>)
    await userEvent.click(await screen.findByRole('button', { name: 'Borrar todo' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('¿Borrar todo el historial? Los archivos no se borran.')).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Borrar todo' }))
    await waitFor(() => expect(c.deleteHistory).toHaveBeenCalledWith('all'))
  })
})

describe('LibraryScreen', () => {
  it('marks missing files', async () => {
    const track = { id: 1, title: 'La Graciosa', artist: 'Quevedo', album: '', duration_s: 258, views: 1, path: 'C:/x.mp3', format: 'mp3', added_at: '2026-11-01T10:00:00+00:00', missing: true } as TrackRecord
    const c = { library: vi.fn(async () => [track]) } as any
    window.oneforall = { showInFolder: vi.fn(), openPath: vi.fn() } as any
    render(<EngineTestProvider client={c}><LibraryScreen /></EngineTestProvider>)
    expect(await screen.findByText('No encontrado')).toBeInTheDocument()
  })
})

describe('LibraryScreen analysis', () => {
  const t = (id: number, title: string, over: Partial<TrackRecord> = {}) =>
    ({ id, title, artist: 'A', album: '', duration_s: 200, views: 1, path: `C:/${title}.mp3`, format: 'mp3', added_at: '2026-11-01T10:00:00+00:00', missing: false, bpm: null, camelot: null, lufs: null, ...over }) as TrackRecord

  it('shows bpm, key chip and lufs, and analyses the selected rows', async () => {
    const c = {
      library: vi.fn(async () => [t(1, 'Uno', { bpm: 128, camelot: '8A', lufs: -9.1 }), t(2, 'Dos')]),
      analyze: vi.fn(async () => ({ jobs: [] }))
    } as any
    window.oneforall = { showInFolder: vi.fn(), openPath: vi.fn(), pathForFile: (f: File) => `C:/${f.name}` } as any
    render(<EngineTestProvider client={c}><LibraryScreen /></EngineTestProvider>)
    expect(await screen.findByText('128.0')).toBeInTheDocument()
    expect(screen.getByText('8A')).toBeInTheDocument()
    expect(screen.getByText('-9.1')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar Uno' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar Dos' }))
    await userEvent.click(screen.getByRole('button', { name: 'Analizar seleccionadas (2)' }))
    expect(c.analyze).toHaveBeenCalledWith(['C:/Uno.mp3', 'C:/Dos.mp3'])
  })
})
