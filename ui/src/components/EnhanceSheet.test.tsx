import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EnhanceSheet } from './EnhanceSheet'
import { EngineTestProvider } from '../lib/engine'
import { useJobsStore } from '../stores/jobsStore'

const A = { path: 'C:/m/A.mp3', enhanced: false }
const B = { path: 'C:/m/B.mp3', enhanced: false }

function client(over: Record<string, unknown> = {}) {
  return {
    enhance: vi.fn(async () => ({ job: { id: 'e1' } })),
    enhancePreview: vi.fn(async () => ({ job: { id: 'p1' } })),
    enhanceEstimate: vi.fn(async () => ({ seconds: null })),
    audioUrl: (p: string) => `http://x/audio?path=${p}`,
    ...over
  } as any
}

function setup(items = [A], c = client()) {
  const onClose = vi.fn()
  render(
    <EngineTestProvider client={c}>
      <EnhanceSheet items={items} onClose={onClose} />
    </EngineTestProvider>
  )
  return { c, onClose }
}

beforeEach(() => useJobsStore.getState().reset())

describe('EnhanceSheet', () => {
  it('defaults to a new copy in the same format; replace warns about Originales', async () => {
    setup()
    expect(screen.getByRole('radio', { name: 'Copia nueva' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Mismo formato' })).toBeChecked()
    expect(screen.queryByText('El original se guarda en Originales')).toBeNull()
    await userEvent.click(screen.getByRole('radio', { name: 'Reemplazar el original' }))
    expect(screen.getByText('El original se guarda en Originales')).toBeInTheDocument()
  })

  it('queues one job per track with the chosen options and closes', async () => {
    const { c, onClose } = setup([A, B])
    await userEvent.click(screen.getByRole('radio', { name: 'Reemplazar el original' }))
    await userEvent.click(screen.getByRole('radio', { name: 'FLAC' }))
    await userEvent.click(screen.getByRole('button', { name: 'Mejorar' }))
    expect(c.enhance).toHaveBeenCalledTimes(2)
    expect(c.enhance).toHaveBeenCalledWith('C:/m/A.mp3', 'replace', 'flac')
    expect(c.enhance).toHaveBeenCalledWith('C:/m/B.mp3', 'replace', 'flac')
    expect(onClose).toHaveBeenCalled()
  })

  it('warns when a track is already enhanced', () => {
    setup([{ ...A, enhanced: true }])
    expect(screen.getByText('Ya está mejorada; mejorarla otra vez no suele ayudar')).toBeInTheDocument()
  })

  it('A/B preview: progress, then Original / Mejorado', async () => {
    const { c } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Escuchar antes' }))
    expect(c.enhancePreview).toHaveBeenCalledWith('C:/m/A.mp3')
    const job = { id: 'p1', type: 'enhance_preview', title: 't', status: 'running', stage: 'restoring', pct: 40, parent_id: null, error: null, result: null, created_at: '' }
    act(() => useJobsStore.getState().setAll([job as any]))
    expect(await screen.findByText('Preparando… 40 %')).toBeInTheDocument()
    act(() => useJobsStore.getState().setAll([{ ...job, status: 'done', result: { original: 'C:/t/o.wav', enhanced: 'C:/t/e.wav', start: 30 } } as any]))
    const orig = await screen.findByRole('button', { name: 'Original' })
    const enh = screen.getByRole('button', { name: 'Mejorado' })
    expect(enh).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(orig)
    expect(orig).toHaveAttribute('aria-pressed', 'true')
    expect(enh).toHaveAttribute('aria-pressed', 'false')
  })

  it('no preview for several tracks', () => {
    setup([A, B])
    expect(screen.queryByRole('button', { name: 'Escuchar antes' })).toBeNull()
  })

  it('shows the estimate per song and in total', async () => {
    setup([A, B], client({ enhanceEstimate: vi.fn(async () => ({ seconds: 120 })) }))
    expect(await screen.findByText('≈ 2 min por canción · 4 min en total')).toBeInTheDocument()
  })

  it('hides the estimate when there is none yet', async () => {
    const c = client()
    setup([A], c)
    await act(async () => undefined)
    expect(c.enhanceEstimate).toHaveBeenCalled()
    expect(screen.queryByText(/por canción/)).toBeNull()
  })

  it('Mejorar is disabled while queueing (no double submit)', async () => {
    let release: () => void = () => undefined
    const c = client({ enhance: vi.fn(() => new Promise((r) => { release = () => r({ job: { id: 'e1' } }) })) })
    setup([A], c)
    const btn = screen.getByRole('button', { name: 'Mejorar' })
    await userEvent.click(btn)
    expect(btn).toBeDisabled()
    await userEvent.click(btn)
    expect(c.enhance).toHaveBeenCalledTimes(1)
    await act(async () => release())
  })

  it('a rejected track does not stop the rest of the batch', async () => {
    const c = client({
      enhance: vi.fn(async (p: string) => {
        if (p === A.path) throw new Error('No se encuentra el archivo')
        return { job: { id: 'e2' } }
      })
    })
    const { onClose } = setup([A, B], c)
    await userEvent.click(screen.getByRole('button', { name: 'Mejorar' }))
    expect(c.enhance).toHaveBeenCalledTimes(2)
    expect(onClose).toHaveBeenCalled()
  })

  it('a failed preview can be retried', async () => {
    const { c } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Escuchar antes' }))
    const job = { id: 'p1', type: 'enhance_preview', title: 't', status: 'failed', stage: 'restoring', pct: 10, parent_id: null, error: { code: 'x', message: 'No se pudo preparar' }, result: null, created_at: '' }
    act(() => useJobsStore.getState().setAll([job as any]))
    await userEvent.click(await screen.findByRole('button', { name: 'Escuchar antes' }))
    expect(c.enhancePreview).toHaveBeenCalledTimes(2)
  })

  it('per-song estimate averages only the tracks that have one', async () => {
    const est = vi.fn(async (p: string) => ({ seconds: p === A.path ? 120 : null }))
    setup([A, B], client({ enhanceEstimate: est }))
    expect(await screen.findByText('≈ 2 min por canción · 2 min en total')).toBeInTheDocument()
  })
})
