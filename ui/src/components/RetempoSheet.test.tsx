import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RetempoSheet } from './RetempoSheet'
import { EngineTestProvider } from '../lib/engine'
import { EngineError } from '../lib/engineClient'
import { retempoName } from '../lib/format'
import { useJobsStore } from '../stores/jobsStore'

const PATH = 'C:/m/Song.mp3'
const record = { path: PATH, bpm: 128, bpm_confidence: 0.8, bpm_source: 'auto', tonic: 'A', mode: 'minor', camelot: '8A', key_confidence: 0.6, lufs: -9, peak_db: -1, version: 2, created_at: '' }
const sidecar = { beats: [], waveform: { peaks: [], low: [], mid: [], high: [] }, duration: 200 }

function client(over: Record<string, unknown> = {}) {
  return {
    getAnalysis: vi.fn(async () => ({ record, sidecar, info: {} })),
    retempo: vi.fn(async () => ({ job: { id: 'r1' } })),
    ...over
  } as any
}

beforeEach(() => {
  useJobsStore.getState().reset()
  window.oneforall = { showInFolder: vi.fn() } as any
})

describe('retempoName', () => {
  it('matches the engine naming', () => {
    expect(retempoName('Song', 128, 124, '8A', 2)).toBe('Song (124 BPM, 10A)')
    expect(retempoName('Song', 128, 128, '8A', 1)).toBe('Song (3A)')
    expect(retempoName('Song', 128, 124.25, null, 0)).toBe('Song (124.2 BPM)')
  })
})

describe('RetempoSheet', () => {
  it('limits the BPM to 50-150 % of the original', async () => {
    render(<EngineTestProvider client={client()}><RetempoSheet path={PATH} onClose={() => undefined} /></EngineTestProvider>)
    const range = await screen.findByRole('slider', { name: 'BPM destino' })
    expect(range).toHaveAttribute('min', '64')
    expect(range).toHaveAttribute('max', '192')
  })

  it('previews the new name and creates the copy', async () => {
    const c = client()
    render(<EngineTestProvider client={c}><RetempoSheet path={PATH} onClose={() => undefined} /></EngineTestProvider>)
    fireEvent.change(await screen.findByRole('slider', { name: 'BPM destino' }), { target: { value: '124' } })
    const up = screen.getByRole('button', { name: 'Subir tono' })
    await userEvent.click(up)
    await userEvent.click(up)
    expect(screen.getByText('Song (124 BPM, 10A)')).toBeInTheDocument()
    expect(screen.getByText('8A → 10A')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Crear copia' }))
    expect(c.retempo).toHaveBeenCalledWith(PATH, 124, 2, undefined)
    const job = { id: 'r1', type: 'retempo', title: 't', status: 'running', stage: 'rendering', pct: 30, parent_id: null, error: null, result: null, created_at: '' }
    act(() => useJobsStore.getState().setAll([job as any]))
    expect(await screen.findByText('Creando copia… 30 %')).toBeInTheDocument()
    act(() => useJobsStore.getState().setAll([{ ...job, status: 'done', result: { path: 'C:/m/Song (124 BPM, 10A).mp3' } } as any]))
    await userEvent.click(await screen.findByRole('button', { name: 'Mostrar en carpeta' }))
    expect(window.oneforall.showInFolder).toHaveBeenCalledWith('C:/m/Song (124 BPM, 10A).mp3')
  })

  it('needs an analysis first', async () => {
    const c = client({ getAnalysis: vi.fn(async () => { throw new EngineError(404, 'not_analyzed', 'Sin analizar') }) })
    render(<EngineTestProvider client={c}><RetempoSheet path={PATH} onClose={() => undefined} /></EngineTestProvider>)
    expect(await screen.findByText('Analiza primero')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Crear copia' })).toBeDisabled()
  })
})
