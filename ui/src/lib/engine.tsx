import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { createClient, type EngineClient } from './engineClient'
import { useJobsStore } from '../stores/jobsStore'
import { useUiStore } from '../stores/uiStore'

type Status = 'connecting' | 'ready' | 'failed'

interface EngineCtx {
  client: EngineClient | null
  status: Status
  retry(): void
}

const Ctx = createContext<EngineCtx>({ client: null, status: 'connecting', retry: () => undefined })

export const useEngine = () => useContext(Ctx)

/** The engine's client; only call inside screens rendered after the engine is ready. */
export function useClient(): EngineClient {
  const { client } = useContext(Ctx)
  if (!client) throw new Error('engine not ready')
  return client
}

export function EngineProvider({ children }: { children: ReactNode }) {
  const [client, setClient] = useState<EngineClient | null>(null)
  const [status, setStatus] = useState<Status>('connecting')
  const [generation, setGeneration] = useState(0)

  useEffect(() => {
    const ui = useUiStore.getState()
    ui.setTheme(ui.theme)
  }, [])

  // (Re)connect whenever the engine (re)starts: port and token change on every start.
  useEffect(() => {
    let disconnect: (() => void) | null = null
    let cancelled = false
    window.oneforall
      .getEngine()
      .then(async (info) => {
        if (cancelled) return
        const c = createClient(info)
        const settings = await c.getSettings().catch(() => null)
        if (settings) {
          useUiStore.getState().setTinted(settings.tinted)
        }
        disconnect = c.connectEvents((e) => {
          if (e.type === 'engine.hello') {
            c.listJobs().then((jobs) => useJobsStore.getState().setAll(jobs)).catch(() => undefined)
          } else {
            useJobsStore.getState().applyEvent(e)
          }
        })
        setClient(c)
        setStatus('ready')
      })
      .catch(() => !cancelled && setStatus('failed'))
    return () => {
      cancelled = true
      disconnect?.()
    }
  }, [generation])

  useEffect(
    () =>
      window.oneforall.onEngineState((s) => {
        if (s === 'restarting') {
          useJobsStore.getState().markEngineReset()
          useUiStore.getState().toast('Reconectando motor…', 'error')
          setStatus('connecting')
        } else if (s === 'ready') {
          setGeneration((g) => g + 1)
        } else if (s === 'failed') {
          setStatus('failed')
        }
      }),
    []
  )

  const retry = () => {
    setStatus('connecting')
    window.oneforall.restartEngine().finally(() => setGeneration((g) => g + 1))
  }

  return <Ctx.Provider value={{ client, status, retry }}>{children}</Ctx.Provider>
}

/** Test helper: renders children against a given (mock) client. */
export function EngineTestProvider({ client, children }: { client: EngineClient; children: ReactNode }) {
  return <Ctx.Provider value={{ client, status: 'ready', retry: () => undefined }}>{children}</Ctx.Provider>
}
