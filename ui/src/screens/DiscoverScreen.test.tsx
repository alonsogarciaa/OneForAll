import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DiscoverScreen } from './DiscoverScreen'
import { EngineTestProvider } from '../lib/engine'
import { useDiscoverStore } from '../stores/discoverStore'
import { useUiStore } from '../stores/uiStore'

const rec = (i: number, over: object = {}) => ({
  kind: 'song', id: `r${i}`, title: `Rec ${i}`, artist: 'Art', album: '', duration_s: 200, views: 10, thumbnail: null,
  url: `https://music.youtube.com/watch?v=r${i}`, track_count: null, in_library: false, source: 'youtube', preview_only: false,
  bpm: null, camelot: null, analysed: false, ...over
})
const seedTrack = { id: 7, video_id: 'seed', title: 'Semilla', artist: 'A', album: '', duration_s: 200, views: null, path: 'C:/s.mp3',
  format: 'mp3', bitrate: null, cover_path: null, added_at: '', bpm: 128, musical_key: 'A minor', camelot: '8A', missing: false }

function client(over: Record<string, unknown> = {}) {
  return {
    library: vi.fn(async () => [seedTrack]),
    similar: vi.fn(async () => ({ seed: rec(0, { id: 'seed', title: 'Semilla' }), items: [rec(1), rec(2), rec(3, { bpm: 64, camelot: '9A', analysed: true })] })),
    quickAnalysis: vi.fn(async () => ({ job: { id: 'q1' } })),
    cancelJob: vi.fn(async () => ({ cancelled: true })),
    moods: vi.fn(async () => [{ title: 'Genres', items: [{ title: 'Reggaetón', params: 'p1' }] }]),
    moodPlaylists: vi.fn(async () => [{ ...rec(9), kind: 'playlist', id: 'PL1', title: 'Perreo' }]),
    getPlaylist: vi.fn(async () => ({ id: 'PL1', title: 'Perreo', tracks: [rec(4), rec(5)] })),
    getSettings: vi.fn(async () => ({ default_format: 'mp3', default_quality: '320' })),
    download: vi.fn(async () => ({ job: { id: 'd1' } })),
    ...over
  } as any
}

beforeEach(() => {
  useDiscoverStore.getState().reset()
  useUiStore.setState({ discoverSeed: 7, toasts: [] })
})

const quick = (video_id: string, bpm: number | null, camelot: string | null, failed = false) =>
  act(() => useDiscoverStore.getState().applyEvent({ type: 'quick.result', video_id, bpm, camelot, failed }))

describe('DiscoverScreen', () => {
  it('loads recommendations for the seed and analyses only the unknown ones', async () => {
    const c = client()
    render(<EngineTestProvider client={c}><DiscoverScreen /></EngineTestProvider>)
    expect(await screen.findByText('Rec 1')).toBeInTheDocument()
    expect(c.similar).toHaveBeenCalledWith({ trackId: 7 })
    expect(c.quickAnalysis).toHaveBeenCalledWith(['r1', 'r2'], [200, 200])
    expect(screen.getAllByText('analizando…')).toHaveLength(2)
  })

  it('events fill the rows and mark the fit against the seed (128 BPM, 8A)', async () => {
    render(<EngineTestProvider client={client()}><DiscoverScreen /></EngineTestProvider>)
    await screen.findByText('Rec 1')
    quick('r1', 128, '8A')
    quick('r2', null, null, true)
    const row1 = screen.getByText('Rec 1').closest('[data-row]') as HTMLElement
    expect(within(row1).getByText('128,0')).toBeInTheDocument()
    expect(within(row1).getByText('Encaja')).toBeInTheDocument()
    const row2 = screen.getByText('Rec 2').closest('[data-row]') as HTMLElement
    expect(within(row2).getAllByText('—').length).toBeGreaterThan(0)
    const row3 = screen.getByText('Rec 3').closest('[data-row]') as HTMLElement
    expect(within(row3).getByText('Encaja')).toBeInTheDocument() // 64 is half of 128, 9A next to 8A
  })

  it('"Mejor encaje" sorts Encaja > Cerca > nothing > pending', async () => {
    render(<EngineTestProvider client={client()}><DiscoverScreen /></EngineTestProvider>)
    await screen.findByText('Rec 1')
    quick('r1', 140, '8A') // cerca (key only)
    await userEvent.click(screen.getByRole('button', { name: 'Mejor encaje' }))
    const titles = screen.getAllByText(/^Rec \d$/).map((e) => e.textContent)
    expect(titles).toEqual(['Rec 3', 'Rec 1', 'Rec 2'])
  })

  it('leaving the screen cancels the analysis; coming back reuses what was analysed', async () => {
    const c = client()
    const { unmount } = render(<EngineTestProvider client={c}><DiscoverScreen /></EngineTestProvider>)
    await screen.findByText('Rec 1')
    quick('r1', 128, '8A')
    unmount()
    expect(c.cancelJob).toHaveBeenCalledWith('q1')
    c.quickAnalysis.mockClear()
    render(<EngineTestProvider client={c}><DiscoverScreen /></EngineTestProvider>)
    await screen.findByText('Rec 1')
    expect(c.quickAnalysis).toHaveBeenCalledWith(['r2'], [200])
  })

  it('no recommendations shows the notice', async () => {
    render(<EngineTestProvider client={client({ similar: vi.fn(async () => ({ seed: null, items: [] })) })}><DiscoverScreen /></EngineTestProvider>)
    expect(await screen.findByText('No se encontraron recomendaciones')).toBeInTheDocument()
  })

  it('moods: a genre, its playlists, then its songs; the manual reference re-marks rows without the engine', async () => {
    const c = client()
    render(<EngineTestProvider client={c}><DiscoverScreen /></EngineTestProvider>)
    await userEvent.click(screen.getByRole('button', { name: 'Moods y géneros' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Reggaetón' }))
    await userEvent.click(await screen.findByRole('button', { name: /Perreo/ }))
    expect(await screen.findByText('Rec 4')).toBeInTheDocument()
    quick('r4', 95, '8A')
    await userEvent.type(screen.getByLabelText('BPM de referencia'), '95')
    await userEvent.type(screen.getByLabelText('Tonalidad de referencia'), '8A')
    const row4 = screen.getByText('Rec 4').closest('[data-row]') as HTMLElement
    expect(within(row4).getByText('Encaja')).toBeInTheDocument()
  })

  it('downloads a recommendation', async () => {
    const c = client()
    render(<EngineTestProvider client={c}><DiscoverScreen /></EngineTestProvider>)
    const row = (await screen.findByText('Rec 1')).closest('[data-row]') as HTMLElement
    await userEvent.click(within(row).getByRole('button', { name: /Descargar en/ }))
    expect(c.download).toHaveBeenCalledWith(expect.objectContaining({ target: expect.objectContaining({ id: 'r1' }) }))
  })

  it('picking a seed from the sidebar entry hides the empty prompt', async () => {
    useUiStore.setState({ discoverSeed: null })
    render(<EngineTestProvider client={client()}><DiscoverScreen /></EngineTestProvider>)
    expect(screen.getByText(/Elige una canción de tu biblioteca para ver/)).toBeInTheDocument()
    act(() => useUiStore.getState().openDiscover(7))
    await screen.findByText('Rec 1')
    expect(screen.queryByText(/Elige una canción de tu biblioteca para ver/)).toBeNull()
  })

  it('a long mood playlist only analyses the first 50 rows', async () => {
    const many = Array.from({ length: 120 }, (_, i) => rec(100 + i))
    const c = client({ getPlaylist: vi.fn(async () => ({ id: 'PL1', title: 'Larga', tracks: many })) })
    render(<EngineTestProvider client={c}><DiscoverScreen /></EngineTestProvider>)
    await userEvent.click(screen.getByRole('button', { name: 'Moods y géneros' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Reggaetón' }))
    await userEvent.click(await screen.findByRole('button', { name: /Perreo/ }))
    await screen.findByText('Rec 100')
    const sent = c.quickAnalysis.mock.calls.at(-1)[0]
    expect(sent).toHaveLength(50)
  })

  it('if the analysis cannot start, the rows show "—" instead of waiting forever', async () => {
    const c = client({ quickAnalysis: vi.fn(async () => { throw new Error('422') }) })
    render(<EngineTestProvider client={c}><DiscoverScreen /></EngineTestProvider>)
    await screen.findByText('Rec 1')
    await act(async () => undefined)
    expect(screen.queryByText('analizando…')).toBeNull()
  })
})
