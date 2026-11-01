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
