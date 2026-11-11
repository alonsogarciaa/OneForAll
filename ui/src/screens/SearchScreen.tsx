import { useCallback, useEffect, useRef, useState } from 'react'
import { SearchX, Search } from 'lucide-react'
import { ResultRow } from '../components/ResultRow'
import { TrackDetailSheet } from '../components/TrackDetailSheet'
import { DuplicateSheet } from '../components/DuplicateSheet'
import { StemsSheet } from '../components/StemsSheet'
import { useClient } from '../lib/engine'
import { useUiStore } from '../stores/uiStore'
import type { ConvertOptions, DownloadRequest, SearchKind, SearchResult, TrackRecord } from '../lib/types'
import './search.css'

const KINDS: { kind: SearchKind; label: string }[] = [
  { kind: 'songs', label: 'Canciones' },
  { kind: 'videos', label: 'Vídeos' },
  { kind: 'playlists', label: 'Playlists' },
  { kind: 'soundcloud', label: 'SoundCloud' }
]
const DEBOUNCE_MS = 400
const IMPORT_LINK = /(open\.spotify\.com\/|^spotify:|spotify\.link\/|music\.apple\.com\/|soundcloud\.com\/)/i

/** YouTube Music sometimes repeats a video; rows are keyed by id, so repeats must go. */
export function uniqueResults(rs: SearchResult[]): SearchResult[] {
  const seen = new Set<string>()
  return rs.filter((r) => {
    const k = `${r.kind}-${r.id}`
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })
}

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
  const [stemsPick, setStemsPick] = useState<SearchResult | null>(null)
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
    if (IMPORT_LINK.test(term)) {
      // Spotify / Apple Music / SoundCloud link: read it and offer to import it, no search
      setLoading(true)
      client
        .discoverLink(term)
        .then((list) => {
          if (my !== seq.current) return
          useUiStore.getState().openImport(list)
          // the link has been used: clear it so coming back to Buscar does not import it again
          useUiStore.setState({ query: '', submittedQuery: '' })
          setTerm('')
        })
        .catch((e) => my === seq.current && toast(e.message, 'error'))
        .finally(() => my === seq.current && setLoading(false))
      return
    }
    setLoading(true)
    client
      .search(term, kind)
      .then((r) => my === seq.current && setResults(uniqueResults(r)))
      .catch((e) => my === seq.current && (toast(e.message, 'error'), setResults([])))
      .finally(() => my === seq.current && setLoading(false))
  }, [client, term, kind, toast])

  const markInLibrary = (id: string) => setResults((rs) => rs?.map((r) => (r.id === id ? { ...r, in_library: true } : r)) ?? rs)

  const startDownload = useCallback(
    async (req: DownloadRequest) => {
      try {
        const r = await client.download(req)
        if ('duplicate' in r) {
          if (req.then_stems) {
            // already in the library: separate the existing file instead of downloading it again
            await client.separate([r.duplicate.path], req.then_stems.stems, req.then_stems.karaoke)
            toast(`«${req.target.title}» ya está en tu biblioteca: separando sus stems`, 'success')
            return
          }
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
  const downloadStems = (item: SearchResult, stems: string[] | null, karaoke = false) => {
    if (stems === null) {
      setStemsPick(item)
      return
    }
    startDownload({ target: item, options, force: false, then_stems: { stems, karaoke } })
  }

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
            <ResultRow
              key={`${r.kind}-${r.id}`}
              item={r}
              options={options}
              onOptions={setOptions}
              onDownload={download}
              onOpen={setDetail}
              onStems={downloadStems}
            />
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
      {stemsPick && (
        <StemsSheet
          paths={[]}
          durationS={stemsPick.duration_s}
          onClose={() => setStemsPick(null)}
          onChoose={(stems, karaoke) => downloadStems(stemsPick, stems, karaoke)}
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
