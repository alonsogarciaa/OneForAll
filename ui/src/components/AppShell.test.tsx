import { render, screen } from '@testing-library/react'
import { AppShell } from './AppShell'
import { useJobsStore } from '../stores/jobsStore'
import type { Job } from '../lib/types'

const running: Job = {
  id: 'a', type: 'download', title: 'La Graciosa', status: 'running', stage: 'downloading', pct: 50,
  parent_id: null, error: null, result: null, children: []
}

beforeEach(() => useJobsStore.getState().reset())

describe('AppShell', () => {
  it('renders the mini queue for active jobs without looping', () => {
    useJobsStore.getState().setAll([running])
    render(<AppShell><p>contenido</p></AppShell>)
    expect(screen.getByText('1 en curso')).toBeInTheDocument()
    expect(screen.getByText('contenido')).toBeInTheDocument()
  })

  it('hides the mini queue when nothing runs', () => {
    render(<AppShell><p>x</p></AppShell>)
    expect(screen.queryByText(/en curso/)).toBeNull()
  })
})
