import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StemsSheet } from './StemsSheet'
import { EngineTestProvider } from '../lib/engine'
import { estimateSeconds } from '../lib/stems'

function client() {
  return { separate: vi.fn(async () => ({ jobs: [] })) } as any
}

describe('StemsSheet', () => {
  it('pre-checks voz, batería, bajo y guitarra', () => {
    render(<EngineTestProvider client={client()}><StemsSheet paths={['C:/a.mp3']} durationS={240} onClose={() => undefined} /></EngineTestProvider>)
    const checked = screen.getAllByRole('checkbox').filter((c) => (c as HTMLInputElement).checked).map((c) => c.getAttribute('aria-label'))
    expect(checked).toEqual(['Voz', 'Batería', 'Bajo', 'Guitarra'])
    expect(screen.getByText('≈ 2 min en este equipo')).toBeInTheDocument()
  })

  it('disables Separar with nothing checked', async () => {
    render(<EngineTestProvider client={client()}><StemsSheet paths={['C:/a.mp3']} durationS={240} onClose={() => undefined} /></EngineTestProvider>)
    for (const name of ['Voz', 'Batería', 'Bajo', 'Guitarra']) await userEvent.click(screen.getByRole('checkbox', { name }))
    expect(screen.getByRole('button', { name: 'Separar' })).toBeDisabled()
  })

  it('sends the chosen stems and the karaoke switch', async () => {
    const c = client()
    const onClose = vi.fn()
    render(<EngineTestProvider client={c}><StemsSheet paths={['C:/a.mp3', 'C:/b.mp3']} durationS={240} onClose={onClose} /></EngineTestProvider>)
    await userEvent.click(screen.getByRole('checkbox', { name: 'Guitarra' }))
    await userEvent.click(screen.getByRole('switch', { name: 'Separar voz principal y coros' }))
    await userEvent.click(screen.getByRole('button', { name: 'Separar' }))
    expect(c.separate).toHaveBeenCalledWith(['C:/a.mp3', 'C:/b.mp3'], ['vocals', 'drums', 'bass'], true)
    expect(onClose).toHaveBeenCalled()
  })
})

describe('estimateSeconds', () => {
  it('uses 0.4 s per audio second without history, else the recent mean', () => {
    expect(estimateSeconds(240)).toBe(96)
    expect(estimateSeconds(100, [0.2, 0.4])).toBe(30)
  })
})
