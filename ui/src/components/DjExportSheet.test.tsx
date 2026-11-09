import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DjExportSheet } from './DjExportSheet'
import { EngineTestProvider } from '../lib/engine'
import { useJobsStore } from '../stores/jobsStore'

function setup(trackIds: number[] | null = [3, 4]) {
  const c = { djExport: vi.fn(async () => ({ job: { id: 'x1' } })), getSettings: vi.fn(async () => ({ music_dir: 'C:/Music' })) } as any
  render(<EngineTestProvider client={c}><DjExportSheet trackIds={trackIds} onClose={() => undefined} /></EngineTestProvider>)
  return c
}

const job = (over: object) => ({ id: 'x1', type: 'dj_export', title: 't', status: 'running', stage: 'writing', pct: 50, parent_id: null, error: null, result: null, created_at: '', ...over })

beforeEach(() => {
  useJobsStore.getState().reset()
  window.oneforall = { pickFolder: vi.fn(async () => 'D:/Export'), showInFolder: vi.fn() } as any
})

describe('DjExportSheet', () => {
  it('exports the whole library to VirtualDJ', async () => {
    const c = setup()
    await userEvent.click(screen.getByRole('radio', { name: /VirtualDJ/ }))
    expect(screen.getByText('Cierra VirtualDJ antes de exportar')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: 'Toda la biblioteca' }))
    await userEvent.click(screen.getByRole('button', { name: 'Exportar' }))
    expect(c.djExport).toHaveBeenCalledWith('virtualdj', null, undefined)
  })

  it('Rekordbox uses the selection and the chosen folder', async () => {
    const c = setup()
    expect(screen.getByRole('radio', { name: 'Seleccionadas (2)' })).toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: 'Elegir carpeta…' }))
    await userEvent.click(screen.getByRole('button', { name: 'Exportar' }))
    expect(c.djExport).toHaveBeenCalledWith('rekordbox', [3, 4], 'D:/Export/OneForAll rekordbox.xml')
  })

  it('shows the summary with the skipped tracks', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: 'Exportar' }))
    act(() => useJobsStore.getState().setAll([job({})] as any))
    expect(await screen.findByText('Exportando… 50 %')).toBeInTheDocument()
    const result = { exported: 5, skipped: [{ title: 'Vieja', reason: 'Sin analizar' }], file: 'C:/Music/OneForAll rekordbox.xml' }
    act(() => useJobsStore.getState().setAll([job({ status: 'done', result })] as any))
    expect(await screen.findByText('5 exportadas · 1 saltadas')).toBeInTheDocument()
    expect(screen.getByText('Vieja — Sin analizar')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Mostrar en carpeta' }))
    expect(window.oneforall.showInFolder).toHaveBeenCalledWith('C:/Music/OneForAll rekordbox.xml')
  })

  it('a failed export shows its message', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: 'Exportar' }))
    act(() => useJobsStore.getState().setAll([job({ status: 'failed', error: { code: 'busy', message: 'Cierra VirtualDJ para exportar' } })] as any))
    expect(await screen.findByText('Cierra VirtualDJ para exportar')).toBeInTheDocument()
  })

  it('without a selection only the whole library is offered', () => {
    setup(null)
    expect(screen.queryByRole('radio', { name: /Seleccionadas/ })).toBeNull()
    expect(screen.getByRole('radio', { name: 'Toda la biblioteca' })).toBeChecked()
  })
})
