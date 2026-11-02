import { AppShell } from './components/AppShell'
import { EngineProvider, useEngine } from './lib/engine'
import { useUiStore } from './stores/uiStore'
import { SearchScreen } from './screens/SearchScreen'
import { DownloadsScreen } from './screens/DownloadsScreen'
import { LibraryScreen } from './screens/LibraryScreen'
import { HistoryScreen } from './screens/HistoryScreen'
import { ConverterScreen } from './screens/ConverterScreen'
import { SettingsScreen } from './screens/SettingsScreen'
import { HarmonyScreen } from './screens/HarmonyScreen'
import { PlaylistSummaryHost } from './components/PlaylistSummarySheet'
import { DataSheet } from './components/DataSheet'

function Screen() {
  const route = useUiStore((s) => s.route)
  if (route === 'buscar') return <SearchScreen />
  if (route === 'descargas') return <DownloadsScreen />
  if (route === 'biblioteca') return <LibraryScreen />
  if (route === 'historial') return <HistoryScreen />
  if (route === 'armonia') return <HarmonyScreen />
  if (route === 'conversor') return <ConverterScreen />
  return <SettingsScreen />
}

function DataSheetHost() {
  const path = useUiStore((s) => s.dataSheet)
  const close = useUiStore((s) => s.closeData)
  return path ? <DataSheet key={path} path={path} onClose={close} /> : null
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
      <DataSheetHost />
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
