import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SearchScreen } from './SearchScreen'
import { EngineTestProvider } from '../lib/engine'
import { useUiStore } from '../stores/uiStore'
import type { SearchResult, TrackRecord } from '../lib/types'

const song = (over: Partial<SearchResult> = {}): SearchResult => ({
  kind: 'song', id: 'v1', title: 'LA GRACIOSA', artist: 'Quevedo, Elvis Crespo', album: 'EL BAIFO', duration_s: 258,
  views: 72_000_000, thumbnail: null, url: 'https://music.youtube.com/watch?v=v1', track_count: null, in_library: false, ...over
})
const dup = { id: 7, title: 'LA GRACIOSA', path: 'C:/m/Quevedo - LA GRACIOSA.mp3' } as TrackRecord

function makeClient(over: Record<string, unknown> = {}) {
  return {
    search: vi.fn(async () => [song(), song({ id: 'v2', title: 'Otra', in_library: true })]),
    getSettings: vi.fn(async () => ({ default_format: 'mp3', default_quality: '320' })),
    download: vi.fn(async () => ({ job: { id: 'j1' } })),
    getPlaylist: vi.fn(),
    downloadPlaylist: vi.fn(),
    ...over
  } as any
}

function setup(client = makeClient()) {
  window.oneforall = { showInFolder: vi.fn() } as any
  render(<EngineTestProvider client={client}><SearchScreen /></EngineTestProvider>)
  return client
}

beforeEach(() => useUiStore.setState({ query: '', submittedQuery: '', toasts: [] }))

describe('SearchScreen', () => {
  it('shows the empty prompt before searching', () => {
    setup()
    expect(screen.getByText('Busca una canción, artista o pega un enlace de YouTube')).toBeInTheDocument()
  })

  it('renders results for a submitted query, with library badge', async () => {
    const c = setup()
    useUiStore.getState().submitQuery('la graciosa')
    expect(await screen.findByText('LA GRACIOSA')).toBeInTheDocument()
    expect(c.search).toHaveBeenCalledWith('la graciosa', 'songs')
    expect(screen.getAllByText('4:18')).toHaveLength(2)
    expect(screen.getAllByText('72 M')).toHaveLength(2)
    expect(screen.getAllByText('En tu biblioteca')).toHaveLength(1)
  })

  it('opens the duplicate sheet and forces the download', async () => {
    const download = vi.fn().mockResolvedValueOnce({ duplicate: dup }).mockResolvedValueOnce({ job: { id: 'j2' } })
    setup(makeClient({ download }))
    useUiStore.getState().submitQuery('la graciosa')
    const row = (await screen.findByText('LA GRACIOSA')).closest('[data-row]') as HTMLElement
    await userEvent.click(within(row).getByRole('button', { name: /Descargar/ }))
    expect(await screen.findByText('Ya tienes esta canción')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Descargar igualmente' }))
    await waitFor(() => expect(download).toHaveBeenCalledTimes(2))
    expect(download.mock.calls[1][0]).toMatchObject({ force: true, options: { format: 'mp3', quality: '320' } })
  })

  it('shows "no results" for an empty search and never mentions BPM', async () => {
    setup(makeClient({ search: vi.fn(async () => []) }))
    useUiStore.getState().submitQuery('zzzz')
    expect(await screen.findByText('Sin resultados para "zzzz"')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/BPM/)
  })

  it('warns that lossless does not add quality', async () => {
    setup()
    useUiStore.getState().submitQuery('la graciosa')
    const row = (await screen.findByText('LA GRACIOSA')).closest('[data-row]') as HTMLElement
    await userEvent.click(within(row).getByRole('button', { name: 'Elegir formato' }))
    await userEvent.selectOptions(screen.getByLabelText('Formato'), 'flac')
    expect(screen.getByText('Convertir audio de YouTube a un formato sin pérdida no aumenta su calidad.')).toBeInTheDocument()
  })
})
