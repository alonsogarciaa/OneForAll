import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MixerSheet } from './MixerSheet'
import { EngineTestProvider } from '../lib/engine'
import { EngineError } from '../lib/engineClient'
import { useUiStore } from '../stores/uiStore'
import { useJobsStore } from '../stores/jobsStore'
import { Metronome } from '../mixer/metronome'

const h = vi.hoisted(() => ({ engines: [] as any[], gate: null as null | Promise<void>, decodeError: null as null | Error }))

vi.mock('../mixer/engine', async () => {
  const { FakeCtx } = await vi.importActual<typeof import('../mixer/fakeAudio')>('../mixer/fakeAudio')
  class MixerEngine {
    playing = false
    duration = 200
    rate = 1
    load = vi.fn(async (stems: unknown[], onP?: (n: number) => void) => stems.forEach((_, i) => onP?.(i + 1)))
    apply = vi.fn()
    play = vi.fn(() => { this.playing = true })
    pause = vi.fn(() => { this.playing = false })
    seek = vi.fn()
    position = vi.fn(() => 0)
    segments = vi.fn(() => [])
    dispose = vi.fn(async () => undefined)
    constructor() { h.engines.push(this) }
  }
  return {
    MixerEngine,
    createAudioContext: () => new FakeCtx(),
    decodeStem: vi.fn(async () => {
      if (h.decodeError) throw h.decodeError
      if (h.gate) { const g = h.gate; h.gate = null; await g }
      return [new Float32Array(441), new Float32Array(441)]
    })
  }
})

const PATH = 'C:/m/a.mp3'
const stems = ['vocals', 'drums', 'bass'].map((stem) => ({ stem, file: `C:/m/Stems/A/${stem}.wav`, size_bytes: 1 }))
const record = { path: PATH, bpm: 128, bpm_confidence: 0.8, bpm_source: 'auto', tonic: 'A', mode: 'minor', camelot: '8A', key_confidence: 0.6, lufs: -9, peak_db: -1, version: 1, created_at: '' }
const sidecar = { beats: [0.5, 0.97, 1.44], waveform: { peaks: [0, 1], low: [0, 1], mid: [0, 0], high: [0, 0] }, duration: 200 }

function client(over: Record<string, unknown> = {}) {
  return {
    getStems: vi.fn(async () => ({ folder: 'C:/m/Stems/A', stems })),
    getAnalysis: vi.fn(async () => ({ record, sidecar, info: {} })),
    getMixerState: vi.fn(async () => ({ state: null })),
    putMixerState: vi.fn(async () => ({ ok: true })),
    mixExport: vi.fn(async () => ({ job: { id: 'm1' } })),
    getSettings: vi.fn(async () => ({ stems_format: 'wav16' })),
    zipStems: vi.fn(async () => ({ zip: 'C:/m/Stems/A/A (stems).zip' })),
    audioUrl: (p: string) => `http://x/audio?path=${p}`,
    ...over
  } as any
}

const eng = () => h.engines[h.engines.length - 1]
const lastApplied = () => eng().apply.mock.calls.at(-1)[0]

function open(c = client()) {
  render(<EngineTestProvider client={c}><MixerSheet path={PATH} onClose={() => undefined} /></EngineTestProvider>)
  return c
}

beforeEach(() => {
  h.engines.length = 0
  h.gate = null
  h.decodeError = null
  globalThis.fetch = vi.fn(async (url: string) => (String(url).includes('missing') ? new Response('', { status: 404 }) : new Response(new ArrayBuffer(8)))) as any
  window.oneforall = { allowDrag: vi.fn(), startDrag: vi.fn(), showInFolder: vi.fn(), openPath: vi.fn() } as any
})

describe('MixerSheet', () => {
  it('shows loading progress, then the strips in mixer order', async () => {
    let release!: () => void
    h.gate = new Promise((r) => (release = r))
    open()
    expect(await screen.findByText('Cargando stems… 0/3')).toBeInTheDocument()
    await act(async () => release())
    expect(await screen.findByRole('button', { name: 'Solo Voz' })).toBeInTheDocument()
    const labels = screen.getAllByTestId('strip-name').map((e) => e.textContent)
    expect(labels).toEqual(['Voz', 'Batería', 'Bajo'])
  })

  it('solo on a strip goes to the engine', async () => {
    open()
    await userEvent.click(await screen.findByRole('button', { name: 'Solo Batería' }))
    expect(lastApplied().stems.drums.solo).toBe(true)
  })

  it('speed preset shows the resulting BPM', async () => {
    open()
    await userEvent.click(await screen.findByRole('button', { name: '0,75×' }))
    expect(lastApplied().rate).toBe(0.75)
    expect(screen.getByText('BPM 128,0 → 96,0')).toBeInTheDocument()
  })

  it('key up shows the resulting Camelot key', async () => {
    open()
    const up = await screen.findByRole('button', { name: 'Subir tono' })
    await userEvent.click(up)
    await userEvent.click(up)
    expect(screen.getByText('8A → 10A')).toBeInTheDocument()
    expect(lastApplied().semis).toBe(2)
  })

  it('saves once, 500 ms after the last of several quick changes', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const c = open()
    const up = await screen.findByRole('button', { name: 'Subir tono' })
    fireEvent.click(up)
    fireEvent.click(up)
    fireEvent.click(up)
    await act(async () => { vi.advanceTimersByTime(400) })
    expect(c.putMixerState).not.toHaveBeenCalled()
    await act(async () => { vi.advanceTimersByTime(200) })
    expect(c.putMixerState).toHaveBeenCalledTimes(1)
    expect(c.putMixerState.mock.calls[0][1].semis).toBe(3)
    vi.useRealTimers()
  })

  it('restores the saved state on open', async () => {
    open(client({ getMixerState: vi.fn(async () => ({ state: { rate: 0.8, semis: -1 } })) }))
    await screen.findByRole('button', { name: 'Solo Voz' })
    expect(lastApplied()).toMatchObject({ rate: 0.8, semis: -1 })
  })

  it('without analysis the metronome is disabled and says why', async () => {
    open(client({ getAnalysis: vi.fn(async () => { throw new EngineError(404, 'not_analyzed', 'Sin analizar') }) }))
    expect(await screen.findByText('Sin BPM')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Metrónomo' })).toBeDisabled()
  })

  it('a missing stem file offers to separate again', async () => {
    const missing = [...stems, { stem: 'piano', file: 'C:/m/Stems/A/missing.wav', size_bytes: 1 }]
    open(client({ getStems: vi.fn(async () => ({ folder: 'C:/m/Stems/A', stems: missing })) }))
    expect(await screen.findByText('Faltan stems de esta canción')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Separar de nuevo' }))
    expect(useUiStore.getState().stemsFor?.paths).toEqual([PATH])
  })

  it('out of memory while decoding shows a clear message', async () => {
    h.decodeError = new RangeError('Array buffer allocation failed')
    open()
    expect(await screen.findByText('No hay memoria suficiente para el mezclador')).toBeInTheDocument()
  })

  it('tracks over 12 minutes are refused before loading', async () => {
    open(client({ getAnalysis: vi.fn(async () => ({ record, sidecar: { ...sidecar, duration: 13 * 60 }, info: {} })) }))
    expect(await screen.findByText('Pista demasiado larga para el mezclador')).toBeInTheDocument()
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('closing during load disposes the engine and never plays', async () => {
    let release!: () => void
    h.gate = new Promise((r) => (release = r))
    const c = client()
    const { unmount } = render(<EngineTestProvider client={c}><MixerSheet path={PATH} onClose={() => undefined} /></EngineTestProvider>)
    await screen.findByText('Cargando stems… 0/3')
    unmount()
    await act(async () => release())
    await waitFor(() => expect(eng().dispose).toHaveBeenCalled())
    expect(eng().play).not.toHaveBeenCalled()
  })

  it('Space toggles play except while typing; L toggles the loop', async () => {
    open(client({ getMixerState: vi.fn(async () => ({ state: { loop: { start: 1, end: 3 } } })) }))
    await screen.findByRole('button', { name: 'Solo Voz' })
    fireEvent.keyDown(document.body, { code: 'Space' })
    await waitFor(() => expect(eng().play).toHaveBeenCalledTimes(1))
    const input = document.createElement('input')
    document.body.appendChild(input)
    fireEvent.keyDown(input, { code: 'Space' })
    expect(eng().pause).not.toHaveBeenCalled()
    input.remove()
    fireEvent.keyDown(document.body, { code: 'KeyL', key: 'l' })
    expect(lastApplied().loop_on).toBe(true)
  })

  it('count-in plays the clicks first, then starts the audio at the returned time', async () => {
    const spy = vi.spyOn(Metronome.prototype, 'countIn').mockReturnValue(7.5)
    open(client({ getMixerState: vi.fn(async () => ({ state: { metronome: { on: true, count_in: 1 } } })) }))
    await userEvent.click(await screen.findByRole('button', { name: 'Reproducir' }))
    await waitFor(() => expect(eng().play).toHaveBeenCalledWith(7.5))
    expect(spy).toHaveBeenCalledWith(1, 128, 1, '4/4', 0.6)
    spy.mockRestore()
  })

  it('meter, count-in and downbeat offset are part of the state', async () => {
    open()
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Compás' }), '3/4')
    expect(lastApplied().metronome.meter).toBe('3/4')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Cuenta atrás' }), '2')
    expect(lastApplied().metronome.count_in).toBe(2)
    await userEvent.click(screen.getByRole('button', { name: 'Mover el 1 a la derecha' }))
    expect(lastApplied().metronome.offset).toBe(1)
  })

  it('loop export is disabled without a loop', async () => {
    open()
    expect(await screen.findByRole('button', { name: 'Solo el bucle' })).toBeDisabled()
  })

  it('exports the full mix with the default format and shows progress, then the draggable result', async () => {
    useJobsStore.getState().reset()
    const c = open()
    await userEvent.click(await screen.findByRole('button', { name: 'Mezcla completa' }))
    expect(c.mixExport).toHaveBeenCalledWith(PATH, expect.objectContaining({ rate: 1 }), 'full', 'wav16')
    const job = { id: 'm1', type: 'mix_export', title: 't', status: 'running', stage: 'rendering', pct: 40, parent_id: null, error: null, result: null, created_at: '' }
    act(() => useJobsStore.getState().setAll([job as any]))
    expect(await screen.findByText('Exportando 40 %')).toBeInTheDocument()
    act(() => useJobsStore.getState().setAll([{ ...job, status: 'done', pct: 100, result: { file: 'C:/m/Stems/A/mix.wav' } } as any]))
    expect(await screen.findByText('mix.wav')).toBeInTheDocument()
    expect(window.oneforall.allowDrag).toHaveBeenCalledWith(['C:/m/Stems/A/mix.wav'])
    await userEvent.click(screen.getByRole('button', { name: 'Mostrar en carpeta' }))
    expect(window.oneforall.showInFolder).toHaveBeenCalledWith('C:/m/Stems/A/mix.wav')
  })

  it('stems zip is available from the export menu', async () => {
    const c = open()
    await userEvent.click(await screen.findByRole('button', { name: 'Stems (zip)' }))
    expect(c.zipStems).toHaveBeenCalledWith(PATH)
  })
})
