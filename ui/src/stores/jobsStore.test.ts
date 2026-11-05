import { useJobsStore, activeJobs, childrenOf } from './jobsStore'
import type { EngineEvent, Job } from '../lib/types'

function job(id: string, over: Partial<Job> = {}): Job {
  return { id, type: 'download', title: id, status: 'queued', stage: 'queued', pct: 0, parent_id: null, error: null, result: null, children: [], ...over }
}
const ev = (type: EngineEvent['type'], j: Job, extra: object = {}) => ({ type, job: j, ...extra }) as EngineEvent

beforeEach(() => useJobsStore.getState().reset())

describe('jobsStore', () => {
  it('applies queued, progress, then done', () => {
    const s = useJobsStore.getState()
    s.applyEvent(ev('job.queued', job('a')))
    s.applyEvent(ev('job.progress', job('a', { status: 'running', stage: 'downloading', pct: 40 }), { speed: '1MiB/s', eta: '00:03' }))
    expect(useJobsStore.getState().jobs.a.pct).toBe(40)
    expect(useJobsStore.getState().meta.a).toEqual({ speed: '1MiB/s', eta: '00:03' })
    s.applyEvent(ev('job.done', job('a', { status: 'done', stage: 'done', pct: 100 })))
    expect(useJobsStore.getState().jobs.a.status).toBe('done')
    expect(useJobsStore.getState().jobs.a.pct).toBe(100)
  })

  it('engine reset fails active jobs and keeps finished ones', () => {
    const s = useJobsStore.getState()
    s.applyEvent(ev('job.progress', job('a', { status: 'running', pct: 40 })))
    s.applyEvent(ev('job.done', job('b', { status: 'done' })))
    s.markEngineReset()
    const { jobs } = useJobsStore.getState()
    expect(jobs.a.status).toBe('failed')
    expect(jobs.a.error?.message).toBe('El motor se reinició')
    expect(jobs.b.status).toBe('done')
  })

  it('selects active jobs and children', () => {
    const s = useJobsStore.getState()
    s.setAll([job('p', { type: 'playlist', status: 'running', children: ['c1', 'c2'] }), job('c1', { parent_id: 'p', status: 'running' }), job('c2', { parent_id: 'p', status: 'done' })])
    const st = useJobsStore.getState()
    expect(activeJobs(st).map((j) => j.id)).toEqual(['c1'])
    expect(childrenOf(st, 'p').map((j) => j.id)).toEqual(['c1', 'c2'])
  })

  it('keeps reset rows when the restarted engine reports no jobs', () => {
    const s = useJobsStore.getState()
    s.applyEvent(ev('job.progress', job('a', { status: 'running', pct: 40 })))
    s.markEngineReset()
    s.setAll([job('n', { status: 'running' })])
    const { jobs, order } = useJobsStore.getState()
    expect(jobs.a.status).toBe('failed')
    expect(jobs.a.error?.message).toBe('El motor se reinició')
    expect(order).toEqual(['a', 'n'])
  })
})
