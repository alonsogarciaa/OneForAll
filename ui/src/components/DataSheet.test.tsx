import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataSheet } from './DataSheet'
import { EngineTestProvider } from '../lib/engine'
import { EngineError } from '../lib/engineClient'

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
    ...over
  } as any
}

beforeEach(() => {
  window.oneforall = { showInFolder: vi.fn() } as any
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
})
