import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StemsSection } from './StemsSection'
import { EngineTestProvider } from '../lib/engine'

const stems = [
  { stem: 'vocals', file: 'C:/m/Stems/A - B/vocals.wav', size_bytes: 1_000_000 },
  { stem: 'drums', file: 'C:/m/Stems/A - B/drums.wav', size_bytes: 2_000_000 },
  { stem: 'bass', file: 'C:/m/Stems/A - B/bass.wav', size_bytes: 3_000_000 }
]

function client(list = stems) {
  return {
    getStems: vi.fn(async () => ({ folder: 'C:/m/Stems/A - B', stems: list })),
    zipStems: vi.fn(async () => ({ zip: 'C:/m/Stems/A - B/A - B (stems).zip' })),
    audioUrl: (p: string) => `http://x/audio?path=${p}`
  } as any
}

beforeEach(() => {
  window.oneforall = { allowDrag: vi.fn(), startDrag: vi.fn(), showInFolder: vi.fn(), openPath: vi.fn() } as any
})

describe('StemsSection', () => {
  it('lists stems, allows dragging them and zips', async () => {
    const c = client()
    render(<EngineTestProvider client={c}><StemsSection path="C:/m/a.mp3" durationS={200} /></EngineTestProvider>)
    expect(await screen.findByText('Voz')).toBeInTheDocument()
    expect(screen.getByText('Batería')).toBeInTheDocument()
    expect(window.oneforall.allowDrag).toHaveBeenCalledWith(stems.map((s) => s.file))
    await userEvent.click(screen.getByRole('button', { name: 'Exportar zip' }))
    expect(c.zipStems).toHaveBeenCalledWith('C:/m/a.mp3')
  })

  it('offers to separate when there are none', async () => {
    render(<EngineTestProvider client={client([])}><StemsSection path="C:/m/a.mp3" durationS={200} /></EngineTestProvider>)
    expect(await screen.findByText('Aún no hay stems')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Separar stems…' })).toBeInTheDocument()
  })
})
