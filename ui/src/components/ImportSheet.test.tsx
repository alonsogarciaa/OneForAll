import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ImportSheet } from './ImportSheet'
import { EngineTestProvider } from '../lib/engine'
import { useDiscoverStore } from '../stores/discoverStore'
import type { ImportList, SearchResult } from '../lib/types'

const yt = (id: string, title = id): SearchResult => ({
  kind: 'song', id, title, artist: 'Art', album: '', duration_s: 200, views: null, thumbnail: null,
  url: `https://music.youtube.com/watch?v=${id}`, track_count: null, in_library: false
})
const LIST: ImportList = {
  name: 'Mi lista', service: 'spotify', truncated: false,
  items: [{ title: 'Uno', artist: 'A', duration_s: 200 }, { title: 'Dos', artist: 'B', duration_s: 210 }, { title: 'Tres', artist: 'C', duration_s: 190 }]
}

function client(over: Record<string, unknown> = {}) {
  return {
    importMatch: vi.fn(async () => ({ job: { id: 'm1' } })),
    startImport: vi.fn(async () => ({ job: { id: 'p1' } })),
    getSettings: vi.fn(async () => ({ default_format: 'mp3', default_quality: '320' })),
    ...over
  } as any
}

function setup(list = LIST, c = client()) {
  const onClose = vi.fn()
  render(<EngineTestProvider client={c}><ImportSheet list={list} onClose={onClose} /></EngineTestProvider>)
  return { c, onClose }
}

const result = (index: number, r: object) =>
  act(() => useDiscoverStore.getState().applyEvent({ type: 'match.result', job_id: 'm1', index, result: r as any }))

beforeEach(() => useDiscoverStore.getState().reset())

describe('ImportSheet', () => {
  it('matches the list and fills the rows from the events', async () => {
    const { c } = setup()
    expect(screen.getByText('Mi lista')).toBeInTheDocument()
    expect(screen.getByText('Spotify')).toBeInTheDocument()
    await act(async () => undefined)
    expect(c.importMatch).toHaveBeenCalledWith(LIST.items)
    result(0, { status: 'found', best: yt('y1', 'Uno (YT)'), alternatives: [] })
    result(1, { status: 'review', best: yt('y2', 'Dos (YT)'), alternatives: [yt('y2b', 'Dos (live)')] })
    result(2, { status: 'missing', best: null, alternatives: [] })
    const rows = screen.getAllByRole('listitem')
    expect(within(rows[0]).getByText('Uno (YT)')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Revisar')).toBeInTheDocument()
    expect(within(rows[2]).getByText('No encontrada')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Descargar todas \(2\)/ })).toBeInTheDocument()
  })

  it('"Ninguna" drops a row; an alternative can be picked; Descargar todas sends the chosen ones', async () => {
    const { c, onClose } = setup()
    await act(async () => undefined)
    result(0, { status: 'found', best: yt('y1'), alternatives: [] })
    result(1, { status: 'review', best: yt('y2'), alternatives: [yt('y2b')] })
    result(2, { status: 'review', best: yt('y3'), alternatives: [] })
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Elegir para «Dos»' }), 'y2b')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Elegir para «Tres»' }), '')
    await userEvent.click(screen.getByRole('button', { name: /Descargar todas \(2\)/ }))
    expect(c.startImport).toHaveBeenCalledWith('Mi lista', [expect.objectContaining({ id: 'y1' }), expect.objectContaining({ id: 'y2b' })],
      expect.objectContaining({ format: 'mp3' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('warns when Spotify only gave the first 100', () => {
    setup({ ...LIST, truncated: true })
    expect(screen.getByText('Spotify solo muestra las primeras 100')).toBeInTheDocument()
  })

  it('a SoundCloud set needs no matching: every row is ready', async () => {
    const sc: ImportList = {
      name: 'Set', service: 'soundcloud', truncated: false,
      items: [{ title: 'Remix', artist: 'DJ', duration_s: 300, url: 'https://soundcloud.com/dj/remix', id: 'sc:5' }]
    }
    const { c } = setup(sc)
    await act(async () => undefined)
    expect(c.importMatch).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: /Descargar todas \(1\)/ }))
    expect(c.startImport).toHaveBeenCalledWith('Set', [expect.objectContaining({ id: 'sc:5', kind: 'soundcloud', url: 'https://soundcloud.com/dj/remix' })],
      expect.anything())
  })

  it('nothing chosen: the button is disabled', async () => {
    setup({ ...LIST, items: [LIST.items[0]] })
    await act(async () => undefined)
    result(0, { status: 'missing', best: null, alternatives: [] })
    expect(screen.getByRole('button', { name: /Descargar todas \(0\)/ })).toBeDisabled()
  })
})
