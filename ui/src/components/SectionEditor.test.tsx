import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SectionEditor } from './SectionEditor'
import { EngineTestProvider } from '../lib/engine'
import type { Section } from '../lib/types'

const sections: Section[] = [
  { start: 0, end: 15, label: 'Intro' },
  { start: 15, end: 45, label: 'Estribillo/Drop' },
  { start: 45, end: 60, label: 'Outro' }
]
const bars = Array.from({ length: 40 }, (_, i) => i * 1.875)

function setup(position = 33.1) {
  const putSections = vi.fn(async (_p: string, s: Section[] | null) => ({ sections: (s ?? sections).map((x) => ({ ...x, source: 'manual' })) }))
  const onChange = vi.fn()
  render(
    <EngineTestProvider client={{ putSections } as any}>
      <SectionEditor path="C:/m/a.mp3" sections={sections} bars={bars} position={position} onChange={onChange} />
    </EngineTestProvider>
  )
  return { putSections, onChange }
}

describe('SectionEditor', () => {
  it('lists sections with their label', () => {
    setup()
    expect(screen.getAllByRole('combobox').map((s) => (s as HTMLSelectElement).value)).toEqual(['Intro', 'Estribillo/Drop', 'Outro'])
  })

  it('renaming sends the edited list', async () => {
    const { putSections, onChange } = setup()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Etiqueta de la sección 2' }), 'Bajón')
    expect((putSections.mock.calls as any)[0][1][1].label).toBe('Bajón')
    expect(onChange).toHaveBeenCalled()
  })

  it('start to playhead snaps to the bar, or is free with Alt', async () => {
    const { putSections } = setup()
    const btns = screen.getAllByRole('button', { name: 'Inicio al cabezal' })
    expect(btns[0]).toBeDisabled()
    fireEvent.click(btns[1])
    expect((putSections.mock.calls as any)[0][1][1].start).toBe(33.75)
    fireEvent.click(btns[1], { altKey: true })
    expect((putSections.mock.calls as any)[1][1][1].start).toBe(33.1)
  })

  it('split, merge, delete and reset', async () => {
    const { putSections } = setup(30)
    await userEvent.click(screen.getByRole('button', { name: 'Partir en el cabezal' }))
    expect((putSections.mock.calls as any)[0][1]).toHaveLength(4)
    await userEvent.click(screen.getAllByRole('button', { name: 'Unir con la siguiente' })[0])
    expect((putSections.mock.calls as any)[1][1]).toHaveLength(2)
    await userEvent.click(screen.getAllByRole('button', { name: 'Borrar' })[2])
    expect((putSections.mock.calls as any)[2][1]).toHaveLength(2)
    await userEvent.click(screen.getByRole('button', { name: 'Volver al automático' }))
    expect((putSections.mock.calls as any)[3][1]).toBeNull()
  })
})
