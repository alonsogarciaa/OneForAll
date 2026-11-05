import { create } from 'zustand'
import { FINAL_STATUSES, type EngineEvent, type Job } from '../lib/types'

interface JobsState {
  jobs: Record<string, Job>
  order: string[]
  meta: Record<string, { speed: string | null; eta: string | null }>
  applyEvent(e: EngineEvent): void
  setAll(jobs: Job[]): void
  markEngineReset(): void
  reset(): void
}

const isFinal = (j: Job) => FINAL_STATUSES.includes(j.status)

export const useJobsStore = create<JobsState>((set) => ({
  jobs: {},
  order: [],
  meta: {},
  applyEvent(e) {
    if (!('job' in e)) return
    const j = e.job
    set((s) => {
      const meta = { ...s.meta }
      if (e.type === 'job.progress') meta[j.id] = { speed: e.speed ?? null, eta: e.eta ?? null }
      else if (e.type !== 'job.queued') delete meta[j.id]
      const prev = s.jobs[j.id]
      // A late progress event must not resurrect a job that already finished.
      if (prev && isFinal(prev) && !isFinal(j)) return s
      return {
        jobs: { ...s.jobs, [j.id]: j },
        order: s.order.includes(j.id) ? s.order : [...s.order, j.id],
        meta
      }
    })
  },
  setAll(jobs) {
    // The engine's list wins, but finished rows it no longer knows (e.g. after a restart) stay visible.
    set((s) => {
      const server = new Set(jobs.map((j) => j.id))
      const kept = s.order.filter((id) => !server.has(id) && s.jobs[id] && isFinal(s.jobs[id]))
      const merged: Record<string, Job> = Object.fromEntries(kept.map((id) => [id, s.jobs[id]]))
      for (const j of jobs) merged[j.id] = j
      return { jobs: merged, order: [...kept, ...jobs.map((j) => j.id)], meta: {} }
    })
  },
  markEngineReset() {
    set((s) => {
      const jobs = { ...s.jobs }
      for (const [id, j] of Object.entries(jobs)) {
        if (!isFinal(j)) jobs[id] = { ...j, status: 'failed', error: { code: 'engine_reset', message: 'El motor se reinició' } }
      }
      return { jobs, meta: {} }
    })
  },
  reset() {
    set({ jobs: {}, order: [], meta: {} })
  }
}))

type View = Pick<JobsState, 'jobs' | 'order'>

export const allJobs = (s: View): Job[] => s.order.map((id) => s.jobs[id]).filter(Boolean)
export const activeJobs = (s: View): Job[] => allJobs(s).filter((j) => !isFinal(j) && j.type !== 'playlist')
export const childrenOf = (s: View, id: string): Job[] => (s.jobs[id]?.children ?? []).map((c) => s.jobs[c]).filter(Boolean)
export { isFinal }
