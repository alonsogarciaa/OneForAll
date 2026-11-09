import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataSheet } from './DataSheet'
import { EngineTestProvider } from '../lib/engine'
import { EngineError } from '../lib/engineClient'
import { useUiStore } from '../stores/uiStore'

const record = {
  path: 'C:/m/a.mp3', bpm: 128, bpm_confidence: 0.8, bpm_source: 'auto', tonic: 'A', mode: 'minor', camelot: '8A',
  key_confidence: 0.6, lufs: -9.1, peak_db: -0.3, version: 1, created_at: ''
}
const sidecar = { beats: [0.5, 0.97], waveform: { peaks: [0, 1], low: [0, 1], mid: [0, 0], high: [0, 0] }, duration: 213 }
const info = { format: 'mp3', bitrate: 320, sample_rate: 44100 }

function client(over: Record<string, unknown> = {}) {
  return {
    getAnalysis: vi.fn(async () => ({ record, sidecar, info })),
    analyze: vi.fn(async () => ({ jobs: [{ id: 'j1' }] })),
    setManualBpm: vi.fn(async () => ({ ...record, bpm: 120, bpm_source: 'manual' })),
    audioUrl: () => 'http://x/audio',
    getStems: vi.fn(async () => ({ folder: null, stems: [] })),
    ...over
  } as any
}

beforeEach(() => {
  window.oneforall = { showInFolder: vi.fn(), allowDrag: vi.fn(), startDrag: vi.fn() } as any
})

describe('DataSheet', () => {
  it('shows the analysis facts', async () => {
    render(<EngineTestProvider client={client()}><DataSheet path="C:/m/a.mp3" onClose={() => undefined} /></EngineTestProvider>)
    expect(await screen.findByText('128.0')).toBeInTheDocument()
    expect(screen.getByText('8A · Lam')).toBeInTheDocument()
    expect(screen.getByText('-9.1 LUFS')).toBeInTheDocument()
    expect(screen.getByText('3:33')).toBeInTheDocument()
    expect(screen.getByText('MP3 · 320 kbps · 44,1 kHz')).toBeInTheDocument()
  })

  it('applies a tapped tempo as manual BPM', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const c = client()
    render(<EngineTestProvider client={c}><DataSheet path="C:/m/a.mp3" onClose={() => undefined} /></EngineTestProvider>)
    await screen.findByText('128.0')
    const tap = screen.getByRole('button', { name: 'Tap' })
    for (let i = 0; i < 8; i++) {
      fireEvent.click(tap)
      vi.advanceTimersByTime(500)
    }
    expect(screen.getByText('120.0', { selector: '.tap-bpm' })).toBeInTheDocument()
    vi.useRealTimers()
    await userEvent.click(screen.getByRole('button', { name: 'Aplicar' }))
    expect(c.setManualBpm).toHaveBeenCalledWith('C:/m/a.mp3', 120)
  })

  it('starts an analysis when the file was never analysed', async () => {
    const c = client({ getAnalysis: vi.fn(async () => { throw new EngineError(404, 'not_analyzed', 'Sin analizar') }) })
    render(<EngineTestProvider client={c}><DataSheet path="C:/m/new.mp3" onClose={() => undefined} /></EngineTestProvider>)
    await waitFor(() => expect(c.analyze).toHaveBeenCalledTimes(1))
    expect(c.analyze).toHaveBeenCalledWith(['C:/m/new.mp3'])
    expect(await screen.findByText(/Analizando/)).toBeInTheDocument()
  })

  it('shows stems even while the analysis is not available yet', async () => {
    const c = client({
      getAnalysis: vi.fn(async () => { throw new EngineError(404, 'not_analyzed', 'Sin analizar') }),
      getStems: vi.fn(async () => ({ folder: 'C:/s', stems: [{ stem: 'vocals', file: 'C:/s/vocals.wav', size_bytes: 10 }] }))
    })
    render(<EngineTestProvider client={c}><DataSheet path="C:/m/new.mp3" onClose={() => undefined} /></EngineTestProvider>)
    expect(await screen.findByText('Voz')).toBeInTheDocument()
  })

  it('ignores held Space and typing in text fields', async () => {
    render(<EngineTestProvider client={client()}><DataSheet path="C:/m/a.mp3" onClose={() => undefined} /></EngineTestProvider>)
    await screen.findByText('128.0')
    const area = document.createElement('textarea')
    document.body.appendChild(area)
    fireEvent.keyDown(area, { code: 'Space' })
    fireEvent.keyDown(document.body, { code: 'Space', repeat: true })
    expect(screen.getByText('—', { selector: '.tap-bpm' })).toBeInTheDocument()
    area.remove()
  })

  it('offers to go back to the automatic BPM', async () => {
    const c = client({ getAnalysis: vi.fn(async () => ({ record: { ...record, bpm_source: 'manual' }, sidecar, info })) })
    render(<EngineTestProvider client={c}><DataSheet path="C:/m/a.mp3" onClose={() => undefined} /></EngineTestProvider>)
    await userEvent.click(await screen.findByRole('button', { name: 'Volver al automático' }))
    expect(c.analyze).toHaveBeenCalledWith(['C:/m/a.mp3'], { reset_bpm: true })
  })

  it('an old analysis asks to re-analyse for sections', async () => {
    const c = client({ getAnalysis: vi.fn(async () => ({ record, sidecar: { ...sidecar, needs_reanalysis: true }, info })) })
    render(<EngineTestProvider client={c}><DataSheet path="C:/m/a.mp3" onClose={() => undefined} /></EngineTestProvider>)
    expect(await screen.findByText('Reanaliza para detectar secciones')).toBeInTheDocument()
  })

  it('the Rejilla toggle reveals the grid controls and a grid change reloads the analysis', async () => {
    const grid = { anchor: 0.5, bpm: 128, source: 'auto', meter: 4 }
    const c = client({
      getAnalysis: vi.fn(async () => ({ record, sidecar: { ...sidecar, grid }, info })),
      putGrid: vi.fn(async () => ({ grid: { ...grid, anchor: 0.97, source: 'manual' } }))
    })
    render(<EngineTestProvider client={c}><DataSheet path="C:/m/a.mp3" onClose={() => undefined} /></EngineTestProvider>)
    await screen.findByText('128.0')
    expect(screen.queryByRole('button', { name: '+1 golpe' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Rejilla' }))
    await userEvent.click(screen.getByRole('button', { name: '+1 golpe' }))
    expect(c.putGrid).toHaveBeenCalledWith('C:/m/a.mp3', { shift_beats: 1 })
    await waitFor(() => expect(c.getAnalysis).toHaveBeenCalledTimes(2))
  })

  it('shows the sections and their editor', async () => {
    const sections = [{ start: 0, end: 100, label: 'Intro' }, { start: 100, end: 213, label: 'Estribillo/Drop' }]
    const grid = { anchor: 0.5, bpm: 128, source: 'auto', meter: 4 }
    const c = client({ getAnalysis: vi.fn(async () => ({ record, sidecar: { ...sidecar, grid, sections }, info })) })
    render(<EngineTestProvider client={c}><DataSheet path="C:/m/a.mp3" onClose={() => undefined} /></EngineTestProvider>)
    expect(await screen.findByRole('combobox', { name: 'Etiqueta de la sección 2' })).toHaveValue('Estribillo/Drop')
  })

  it('opens the change BPM and key sheet', async () => {
    render(<EngineTestProvider client={client()}><DataSheet path="C:/m/a.mp3" onClose={() => undefined} /></EngineTestProvider>)
    await userEvent.click(await screen.findByRole('button', { name: /Cambiar BPM y tono/ }))
    expect(useUiStore.getState().retempoFor).toBe('C:/m/a.mp3')
  })
})
