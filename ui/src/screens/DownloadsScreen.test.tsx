import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DownloadsScreen } from './DownloadsScreen'
import { PlaylistSummaryHost } from '../components/PlaylistSummarySheet'
import { EngineTestProvider } from '../lib/engine'
import { useJobsStore } from '../stores/jobsStore'
import type { Job } from '../lib/types'

function job(id: string, over: Partial<Job> = {}): Job {
  return { id, type: 'download', title: `Canción ${id}`, status: 'running', stage: 'downloading', pct: 40, parent_id: null, error: null, result: null, children: [], ...over }
}

function setup(client: any = { cancelJob: vi.fn(async () => ({ cancelled: true })), download: vi.fn(async () => ({ job: job('r') })) }) {
  window.oneforall = { showInFolder: vi.fn() } as any
  render(
    <EngineTestProvider client={client}>
      <DownloadsScreen />
      <PlaylistSummaryHost />
    </EngineTestProvider>
  )
  return client
}

const rowOf = (title: string) => screen.getByText(title).closest('[data-job]') as HTMLElement

beforeEach(() => useJobsStore.getState().reset())

describe('DownloadsScreen', () => {
  it('shows an empty state with no jobs', () => {
    setup()
    expect(screen.getByText('No hay descargas todavía')).toBeInTheDocument()
  })

  it('cancels only the chosen job', async () => {
    useJobsStore.getState().setAll([job('A'), job('B')])
    const c = setup()
    await userEvent.click(within(rowOf('Canción A')).getByRole('button', { name: 'Cancelar' }))
    expect(c.cancelJob).toHaveBeenCalledTimes(1)
    expect(c.cancelJob).toHaveBeenCalledWith('A')
  })

  it('stops the animation and shows Cancelado after job.cancelled', () => {
    useJobsStore.getState().setAll([job('A')])
    setup()
    expect(rowOf('Canción A').querySelector('.is-animating')).not.toBeNull()
    act(() => useJobsStore.getState().applyEvent({ type: 'job.cancelled', job: job('A', { status: 'cancelled', stage: 'cancelled', pct: 0 }) }))
    expect(rowOf('Canción A').querySelector('.is-animating')).toBeNull()
    expect(within(rowOf('Canción A')).getByText('Cancelado')).toBeInTheDocument()
    expect(within(rowOf('Canción A')).queryByRole('button', { name: 'Cancelar' })).toBeNull()
  })

  it('retries a failed download with its original request', async () => {
    const request = { target: { id: 'v1', title: 'Canción A' }, options: { format: 'mp3' } }
    useJobsStore.getState().setAll([job('A', { status: 'failed', error: { code: 'offline', message: 'Sin conexión' }, payload: { request } })])
    const c = setup()
    expect(within(rowOf('Canción A')).getByText('Sin conexión')).toBeInTheDocument()
    await userEvent.click(within(rowOf('Canción A')).getByRole('button', { name: 'Reintentar' }))
    expect(c.download).toHaveBeenCalledWith({ ...request, force: true })
  })

  it('opens the playlist summary when a playlist finishes', () => {
    const parent = job('P', { type: 'playlist', title: 'Mi lista', children: [] })
    useJobsStore.getState().setAll([parent])
    setup()
    act(() =>
      useJobsStore.getState().applyEvent({
        type: 'job.done',
        job: { ...parent, status: 'done', result: { done: 8, skipped: 1, cancelled: 0, failed: [{ title: 'X', code: 'unavailable', message: 'Este vídeo ya no está disponible', target: {} }], options: { format: 'mp3' } } }
      })
    )
    expect(screen.getByText('8 descargadas · 1 fallidas · 1 ya en tu biblioteca')).toBeInTheDocument()
    expect(screen.getByText('Este vídeo ya no está disponible')).toBeInTheDocument()
  })
})
