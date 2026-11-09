import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GridControls } from './GridControls'
import { EngineTestProvider } from '../lib/engine'

vi.mock('../mixer/engine', async () => {
  const { FakeCtx } = await vi.importActual<typeof import('../mixer/fakeAudio')>('../mixer/fakeAudio')
  return { createAudioContext: () => new FakeCtx() }
})

const grid = { anchor: 0.5, bpm: 128, source: 'auto' as const, meter: 4 }

function setup() {
  const putGrid = vi.fn(async (_p: string, op: Record<string, unknown>) => ({ grid: { ...grid, source: 'manual', ...op } }))
  const onChange = vi.fn()
  render(
    <EngineTestProvider client={{ putGrid } as any}>
      <GridControls path="C:/m/a.mp3" grid={grid} position={12.5} audio={null} onChange={onChange} />
    </EngineTestProvider>
  )
  return { putGrid, onChange }
}

describe('GridControls', () => {
  it.each([
    ['El 1 aquí', { anchor: 12.5 }],
    ['−10 ms', { shift_ms: -10 }],
    ['+10 ms', { shift_ms: 10 }],
    ['−1 golpe', { shift_beats: -1 }],
    ['+1 golpe', { shift_beats: 1 }],
    ['÷2', { scale: 0.5 }],
    ['×2', { scale: 2 }],
    ['Volver al automático', { reset: true }]
  ])('%s sends %o', async (name, op) => {
    const { putGrid, onChange } = setup()
    await userEvent.click(screen.getByRole('button', { name }))
    expect(putGrid).toHaveBeenCalledWith('C:/m/a.mp3', op)
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ source: 'manual' }))
  })

  it('shows the grid BPM and toggles the metronome', async () => {
    setup()
    expect(screen.getByText('128,0 BPM · 1 en 0:00.500')).toBeInTheDocument()
    const m = screen.getByRole('button', { name: 'Metrónomo' })
    await userEvent.click(m)
    expect(m).toHaveAttribute('aria-pressed', 'true')
  })
})
