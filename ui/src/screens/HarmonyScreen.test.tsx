import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HarmonyScreen } from './HarmonyScreen'
import { EngineTestProvider } from '../lib/engine'
import type { TrackRecord } from '../lib/types'

const t = (id: number, title: string, camelot: string | null, bpm: number | null) =>
  ({ id, title, artist: 'A', album: '', path: `C:/${title}.mp3`, format: 'mp3', added_at: '', missing: false, camelot, bpm, duration_s: 200, views: null }) as TrackRecord

function client(over: Record<string, unknown> = {}) {
  return {
    library: vi.fn(async () => [t(1, 'Ref', '8A', 128), t(2, 'Sin analizar', null, null)]),
    harmonic: vi.fn(async () => [
      { track: t(3, 'Igual', '8A', 126), level: 'same', bpm_diff_pct: -1.6 },
      { track: t(4, 'Vecina', '9A', 130), level: 'adjacent', bpm_diff_pct: 1.6 }
    ]),
    ...over
  } as any
}

beforeEach(() => {
  window.oneforall = { showInFolder: vi.fn() } as any
})

describe('HarmonyScreen', () => {
  it('searches compatibles for a reference track and shows them in engine order', async () => {
    const c = client()
    render(<EngineTestProvider client={c}><HarmonyScreen /></EngineTestProvider>)
    await userEvent.selectOptions(await screen.findByLabelText('Pista de referencia'), '1')
    await waitFor(() => expect(c.harmonic).toHaveBeenCalledWith({ ref_track: 1, bpm_tolerance: 6 }))
    const rows = await screen.findAllByTestId('harmonic-row')
    expect(rows.map((r) => r.textContent)).toEqual([expect.stringContaining('Igual'), expect.stringContaining('Vecina')])
    expect(screen.getByText('Misma clave')).toBeInTheDocument()
    expect(screen.getByText('±1')).toBeInTheDocument()
    expect(screen.getByText('−1,6 %')).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Sin analizar/ })).toBeNull()
  })

  it('supports manual bpm and key', async () => {
    const c = client()
    render(<EngineTestProvider client={c}><HarmonyScreen /></EngineTestProvider>)
    await userEvent.click(await screen.findByRole('button', { name: 'Manual' }))
    await userEvent.type(screen.getByLabelText('BPM de referencia'), '128')
    await userEvent.selectOptions(screen.getByLabelText('Tonalidad de referencia'), '8A')
    await waitFor(() => expect(c.harmonic).toHaveBeenLastCalledWith({ bpm: 128, camelot: '8A', bpm_tolerance: 6 }))
  })

  it('explains what to do when nothing is analysed', async () => {
    render(<EngineTestProvider client={client({ library: vi.fn(async () => []) })}><HarmonyScreen /></EngineTestProvider>)
    expect(await screen.findByText('Analiza canciones de tu biblioteca para ver compatibles')).toBeInTheDocument()
  })
})
