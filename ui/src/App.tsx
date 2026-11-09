import { AppShell } from './components/AppShell'
import { EngineProvider, useEngine } from './lib/engine'
import { useUiStore } from './stores/uiStore'
import { SearchScreen } from './screens/SearchScreen'
import { DiscoverScreen } from './screens/DiscoverScreen'
import { DownloadsScreen } from './screens/DownloadsScreen'
import { LibraryScreen } from './screens/LibraryScreen'
import { HistoryScreen } from './screens/HistoryScreen'
import { ConverterScreen } from './screens/ConverterScreen'
import { SettingsScreen } from './screens/SettingsScreen'
import { HarmonyScreen } from './screens/HarmonyScreen'
import { MixerSheet } from './components/MixerSheet'
import { RetempoSheet } from './components/RetempoSheet'
import { DjExportSheet } from './components/DjExportSheet'
import { EnhanceSheet } from './components/EnhanceSheet'
import { VideoExportSheet } from './components/VideoExportSheet'
import { ImportSheet } from './components/ImportSheet'
import { PlaylistSummaryHost } from './components/PlaylistSummarySheet'
import { DataSheet } from './components/DataSheet'
import { StemsSheet } from './components/StemsSheet'

function Screen() {
  const route = useUiStore((s) => s.route)
  if (route === 'buscar') return <SearchScreen />
  if (route === 'descubrir') return <DiscoverScreen />
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

function StemsSheetHost() {
  const stemsFor = useUiStore((s) => s.stemsFor)
  const close = useUiStore((s) => s.closeStems)
  return stemsFor ? <StemsSheet paths={stemsFor.paths} durationS={stemsFor.durationS} onClose={close} /> : null
}

function MixerSheetHost() {
  const path = useUiStore((s) => s.mixerFor)
  const close = useUiStore((s) => s.closeMixer)
  return path ? <MixerSheet key={path} path={path} onClose={close} /> : null
}

function RetempoSheetHost() {
  const path = useUiStore((s) => s.retempoFor)
  const close = useUiStore((s) => s.closeRetempo)
  return path ? <RetempoSheet key={path} path={path} onClose={close} /> : null
}

function EnhanceSheetHost() {
  const items = useUiStore((s) => s.enhanceFor)
  const close = useUiStore((s) => s.closeEnhance)
  return items ? <EnhanceSheet items={items} onClose={close} /> : null
}

function ImportSheetHost() {
  const list = useUiStore((s) => s.importList)
  const close = useUiStore((s) => s.closeImport)
  return list ? <ImportSheet key={list.name} list={list} onClose={close} /> : null
}

function VideoExportSheetHost() {
  const v = useUiStore((s) => s.videoExport)
  const close = useUiStore((s) => s.closeVideoExport)
  return v ? <VideoExportSheet trackIds={v.trackIds} onClose={close} /> : null
}

function DjExportSheetHost() {
  const djExport = useUiStore((s) => s.djExport)
  const close = useUiStore((s) => s.closeDjExport)
  return djExport ? <DjExportSheet trackIds={djExport.trackIds} onClose={close} /> : null
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
      <DataSheetHost />
      <StemsSheetHost />
      <MixerSheetHost />
      <RetempoSheetHost />
      <DjExportSheetHost />
      <EnhanceSheetHost />
      <VideoExportSheetHost />
      <ImportSheetHost />
    </>
  )
}

export function App() {
  return (
    <EngineProvider>
      <AppShell>
        <Body />
        <PlaylistSummaryHost />
      </AppShell>
    </EngineProvider>
  )
}
