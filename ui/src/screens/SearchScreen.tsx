import { useCallback, useEffect, useRef, useState } from 'react'
import { SearchX, Search } from 'lucide-react'
import { ResultRow } from '../components/ResultRow'
import { TrackDetailSheet } from '../components/TrackDetailSheet'
import { DuplicateSheet } from '../components/DuplicateSheet'
import { useClient } from '../lib/engine'
import { useUiStore } from '../stores/uiStore'
import type { ConvertOptions, DownloadRequest, SearchKind, SearchResult, TrackRecord } from '../lib/types'
import './search.css'

const KINDS: { kind: SearchKind; label: string }[] = [
  { kind: 'songs', label: 'Canciones' },
  { kind: 'videos', label: 'Vídeos' },
  { kind: 'playlists', label: 'Playlists' }
]
const DEBOUNCE_MS = 400

export function SearchScreen() {
  const client = useClient()
  const query = useUiStore((s) => s.query)
  const submitted = useUiStore((s) => s.submittedQuery)
  const toast = useUiStore((s) => s.toast)

  const [kind, setKind] = useState<SearchKind>('songs')
  const [term, setTerm] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [options, setOptions] = useState<ConvertOptions>({ format: 'mp3', quality: '320' })
  const [detail, setDetail] = useState<SearchResult | null>(null)
  const [duplicate, setDuplicate] = useState<{ track: TrackRecord; req: DownloadRequest } | null>(null)
  const seq = useRef(0)

  useEffect(() => {
    client
      .getSettings()
      .then((s) => setOptions({ format: s.default_format, quality: s.default_format === 'mp3' ? s.default_quality : null }))
      .catch(() => undefined)
  }, [client])

  // Submitted (Enter) wins immediately; typing searches after a short pause.
  useEffect(() => setTerm(submitted), [submitted])
  useEffect(() => {
    const q = query.trim()
    if (q.length < 2 || q === term) return
    const t = setTimeout(() => setTerm(q), DEBOUNCE_MS)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query])

  useEffect(() => {
    if (!term) return
    const my = ++seq.current
    setLoading(true)
    client
      .search(term, kind)
      .then((r) => my === seq.current && setResults(r))
      .catch((e) => my === seq.current && (toast(e.message, 'error'), setResults([])))
      .finally(() => my === seq.current && setLoading(false))
  }, [client, term, kind, toast])

  const markInLibrary = (id: string) => setResults((rs) => rs?.map((r) => (r.id === id ? { ...r, in_library: true } : r)) ?? rs)

  const startDownload = useCallback(
    async (req: DownloadRequest) => {
      try {
        const r = await client.download(req)
        if ('duplicate' in r) {
          setDuplicate({ track: r.duplicate, req })
          return
        }
        setDuplicate(null)
        markInLibrary(req.target.id)
        toast(`Descargando «${req.target.title}»`, 'success')
      } catch (e: any) {
        toast(e.message, 'error')
      }
    },
    [client, toast]
  )

  const download = (item: SearchResult) => startDownload({ target: item, options, force: false })

  const downloadPlaylist = async (id: string, count: number) => {
    try {
      await client.downloadPlaylist(id, options)
      setDetail(null)
      toast(`Descargando ${count} canciones`, 'success')
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  return (
    <section className="search-screen">
      <div className="screen-head">
        <h1 className="screen-title">Buscar</h1>
        <div className="segmented" role="group" aria-label="Tipo de resultado">
          {KINDS.map((k) => (
            <button key={k.kind} aria-pressed={kind === k.kind} onClick={() => setKind(k.kind)}>
              {k.label}
            </button>
          ))}
        </div>
      </div>

      {!term && (
        <div className="empty">
          <Search size={40} strokeWidth={1.4} />
          <p>Busca una canción, artista o pega un enlace de YouTube</p>
        </div>
      )}
      {term && results && results.length === 0 && !loading && (
        <div className="empty">
          <SearchX size={40} strokeWidth={1.4} />
          <p>Sin resultados para "{term}"</p>
        </div>
      )}
      {term && results && results.length > 0 && (
        <div className="results" aria-busy={loading}>
          {results.map((r) => (
            <ResultRow key={`${r.kind}-${r.id}`} item={r} options={options} onOptions={setOptions} onDownload={download} onOpen={setDetail} />
          ))}
        </div>
      )}
      {term && !results && loading && <div className="results-loading" aria-label="Buscando" />}

      {detail && (
        <TrackDetailSheet
          item={detail}
          options={options}
          onOptions={setOptions}
          onDownload={(i) => (setDetail(null), download(i))}
          onDownloadPlaylist={downloadPlaylist}
          onClose={() => setDetail(null)}
        />
      )}
      {duplicate && (
        <DuplicateSheet
          track={duplicate.track}
          onForce={() => startDownload({ ...duplicate.req, force: true })}
          onClose={() => setDuplicate(null)}
        />
      )}
    </section>
  )
}
