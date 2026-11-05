import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Disc3, Download, FolderClock, History, Info, Library, Repeat, Search, Settings2, X } from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'
import { useUiStore, type Route } from '../stores/uiStore'
import { useJobsStore, activeJobs } from '../stores/jobsStore'

const NAV: { route: Route; label: string; icon: typeof Search }[] = [
  { route: 'buscar', label: 'Buscar', icon: Search },
  { route: 'descargas', label: 'Descargas', icon: Download },
  { route: 'biblioteca', label: 'Biblioteca', icon: Library },
  { route: 'armonia', label: 'Armonía', icon: Disc3 },
  { route: 'historial', label: 'Historial', icon: History },
  { route: 'conversor', label: 'Conversor', icon: Repeat }
]

function Sidebar() {
  const route = useUiStore((s) => s.route)
  const navigate = useUiStore((s) => s.navigate)
  const active = useJobsStore((s) => activeJobs(s).length)
  const item = ({ route: r, label, icon: Icon }: (typeof NAV)[number]) => (
    <button key={r} className="nav-item" aria-current={route === r ? 'page' : undefined} onClick={() => navigate(r)}>
      <Icon size={18} strokeWidth={1.8} />
      {label}
      {r === 'descargas' && active > 0 && <span className="nav-count tabular">{active}</span>}
    </button>
  )
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        One<span>For</span>All
      </div>
      <nav className="nav" aria-label="Secciones">
        {NAV.map(item)}
      </nav>
      <div className="sidebar-spacer" />
      <MiniQueue />
      <nav className="nav" aria-label="Preferencias">
        {item({ route: 'ajustes', label: 'Ajustes', icon: Settings2 })}
      </nav>
    </aside>
  )
}

export function MiniQueue() {
  // useShallow: activeJobs builds a new array each call, which would re-render forever.
  const jobs = useJobsStore(useShallow((s) => activeJobs(s)))
  const navigate = useUiStore((s) => s.navigate)
  if (jobs.length === 0) return null
  const pct = jobs.reduce((a, j) => a + j.pct, 0) / jobs.length
  return (
    <button className="mini-queue glass" onClick={() => navigate('descargas')} aria-label={`${jobs.length} procesos en curso`}>
      <div className="mini-queue-row">
        <span>
          <FolderClock size={15} style={{ verticalAlign: '-2px', marginRight: 6 }} />
          {jobs.length} en curso
        </span>
        <span className="tabular">{Math.round(pct)}%</span>
      </div>
      <div className="progress" aria-hidden>
        <div style={{ width: `${pct}%` }} />
      </div>
    </button>
  )
}

function TopBar() {
  const query = useUiStore((s) => s.query)
  const setQuery = useUiStore((s) => s.setQuery)
  const submitQuery = useUiStore((s) => s.submitQuery)
  return (
    <header className="topbar">
      <form
        className="search-pill glass"
        role="search"
        onSubmit={(e) => {
          e.preventDefault()
          submitQuery(query)
        }}
      >
        <Search size={16} />
        <input
          aria-label="Buscar en YouTube Music"
          placeholder="Canción, artista o enlace de YouTube"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          spellCheck={false}
        />
      </form>
    </header>
  )
}

function Toasts() {
  const toasts = useUiStore((s) => s.toasts)
  const dismiss = useUiStore((s) => s.dismissToast)
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((t) => {
        const Icon = t.kind === 'error' ? AlertCircle : t.kind === 'success' ? CheckCircle2 : Info
        return (
          <div key={t.id} className="toast glass" data-kind={t.kind}>
            <Icon size={18} />
            <span>{t.text}</span>
            <button className="btn btn-ghost icon-btn btn-sm" aria-label="Descartar aviso" onClick={() => dismiss(t.id)}>
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}

const AUDIO_RE = /\.(mp3|m4a|aac|wav|aif|aiff|flac|ogg|opus|webm)$/i

export function AppShell({ children }: { children: ReactNode }) {
  const openData = useUiStore((s) => s.openData)
  return (
    <div
      className="app-shell"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault()
        const f = Array.from(e.dataTransfer.files).find((x) => AUDIO_RE.test(x.name))
        if (f && window.oneforall?.pathForFile) openData(window.oneforall.pathForFile(f))
      }}
    >
      <Sidebar />
      <main className="main">
        <TopBar />
        <div className="content">{children}</div>
      </main>
      <Toasts />
    </div>
  )
}
