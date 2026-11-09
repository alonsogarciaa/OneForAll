import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { VideoExportSheet } from './VideoExportSheet'
import { EngineTestProvider } from '../lib/engine'
import { useJobsStore } from '../stores/jobsStore'

function setup(trackIds = [3, 4, 5]) {
  const c = {
    videoExport: vi.fn(async () => ({ job: { id: 'v1' } })),
    getSettings: vi.fn(async () => ({ music_dir: 'C:/Music', videos_dir: null }))
  } as any
  render(<EngineTestProvider client={c}><VideoExportSheet trackIds={trackIds} onClose={() => undefined} /></EngineTestProvider>)
  return c
}

const job = (over: object) => ({ id: 'v1', type: 'video_export', title: 't', status: 'running', stage: 'rendering', pct: 30, parent_id: null, error: null, result: null, created_at: '', ...over })

beforeEach(() => {
  useJobsStore.getState().reset()
  window.oneforall = { pickFolder: vi.fn(async () => 'D:/Vid'), showInFolder: vi.fn() } as any
})

describe('VideoExportSheet', () => {
  it('defaults to 1080p in <music>/Videos and exports the selection', async () => {
    const c = setup()
    expect(screen.getByRole('radio', { name: '1080p' })).toBeChecked()
    expect(await screen.findByText('Se guardará en C:/Music/Videos')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: '720p' }))
    await userEvent.click(screen.getByRole('button', { name: 'Exportar' }))
    expect(c.videoExport).toHaveBeenCalledWith([3, 4, 5], '720', undefined)
  })

  it('uses the chosen folder', async () => {
    const c = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Elegir carpeta…' }))
    expect(screen.getByText('Se guardará en D:/Vid')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Exportar' }))
    expect(c.videoExport).toHaveBeenCalledWith([3, 4, 5], '1080', 'D:/Vid')
  })

  it('shows progress, then the summary with the fallbacks', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: 'Exportar' }))
    act(() => useJobsStore.getState().setAll([job({}) as any]))
    expect(await screen.findByText('Exportando… 30 %')).toBeInTheDocument()
    const result = {
      exported: [{ title: 'A', file: 'C:/Music/Videos/A.mp4' }, { title: 'B', file: 'C:/Music/Videos/B.mp4' }],
      fallbacks: [{ title: 'B', reason: 'Sin vídeo original' }],
      failed: [{ title: 'C', reason: 'No se pudo crear el vídeo' }]
    }
    act(() => useJobsStore.getState().setAll([job({ status: 'done', result }) as any]))
    expect(await screen.findByText('2 exportados · 1 con portada')).toBeInTheDocument()
    expect(screen.getByText('B — Sin vídeo original')).toBeInTheDocument()
    expect(screen.getByText('C — No se pudo crear el vídeo')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Mostrar en carpeta' }))
    expect(window.oneforall.showInFolder).toHaveBeenCalledWith('C:/Music/Videos/A.mp4')
  })

  it('a fallback track that then failed is not counted as "con portada" nor listed twice', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: 'Exportar' }))
    const result = {
      exported: [{ title: 'A', file: 'C:/Music/Videos/A.mp4' }],
      fallbacks: [{ title: 'C', reason: 'Sin vídeo original' }],
      failed: [{ title: 'C', reason: 'No se pudo crear el vídeo' }]
    }
    act(() => useJobsStore.getState().setAll([job({ status: 'done', result }) as any]))
    expect(await screen.findByText('1 exportados · 0 con portada')).toBeInTheDocument()
    expect(screen.getAllByText(/^C — /)).toHaveLength(1)
    expect(screen.getByText('C — No se pudo crear el vídeo')).toBeInTheDocument()
  })
})
