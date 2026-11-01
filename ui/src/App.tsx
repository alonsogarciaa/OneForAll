import { AppShell } from './components/AppShell'
import { EngineProvider, useEngine } from './lib/engine'
import { useUiStore, type Route } from './stores/uiStore'
import { SearchScreen } from './screens/SearchScreen'
import { DownloadsScreen } from './screens/DownloadsScreen'
import { PlaylistSummaryHost } from './components/PlaylistSummarySheet'

const TITLES: Record<Route, string> = {
  buscar: 'Buscar',
  descargas: 'Descargas',
  biblioteca: 'Biblioteca',
  historial: 'Historial',
  conversor: 'Conversor',
  ajustes: 'Ajustes'
}

function Screen() {
  const route = useUiStore((s) => s.route)
  if (route === 'buscar') return <SearchScreen />
  if (route === 'descargas') return <DownloadsScreen />
  // Remaining screens are filled in by later tasks; until then each shows its title.
  return <h1 className="screen-title">{TITLES[route]}</h1>
}

function Body() {
  const { status, retry } = useEngine()
  if (status === 'failed') {
    return (
      <div className="engine-status">
        <div>
          <h2>El motor no responde</h2>
          <p>OneForAll no ha podido arrancar su motor de audio.</p>
          <button className="btn btn-primary" onClick={retry}>
            Reintentar
          </button>
        </div>
      </div>
    )
  }
  if (status === 'connecting') {
    return (
      <div className="engine-status">
        <p>Arrancando el motor…</p>
      </div>
    )
  }
  return (
    <>
      <Screen />
      <PlaylistSummaryHost />
    </>
  )
}

export function App() {
  return (
    <EngineProvider>
      <AppShell>
        <Body />
      </AppShell>
    </EngineProvider>
  )
}
