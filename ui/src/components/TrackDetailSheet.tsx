import { useEffect, useRef, useState } from 'react'
import { GlassSheet } from './GlassSheet'
import { Cover } from './ResultRow'
import { DownloadButton } from './DownloadButton'
import { formatDuration, formatViews } from '../lib/format'
import { useClient } from '../lib/engine'
import type { ConvertOptions, PlaylistInfo, SearchResult } from '../lib/types'

interface Props {
  item: SearchResult
  options: ConvertOptions
  onOptions(o: ConvertOptions): void
  onDownload(item: SearchResult): void
  onDownloadPlaylist(id: string, count: number): void
  onClose(): void
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd className="tabular">{value}</dd>
    </div>
  )
}

function SongDetail({ item }: { item: SearchResult }) {
  return (
    <div className="detail">
      <Cover src={item.thumbnail} size={132} />
      <div>
        <h3 className="detail-title">{item.title}</h3>
        <p className="detail-sub">{item.artist}</p>
        <dl className="facts">
          {item.album && <Fact label="Álbum" value={item.album} />}
          {item.duration_s != null && <Fact label="Duración" value={formatDuration(item.duration_s)} />}
          {item.views != null && <Fact label="Visualizaciones" value={formatViews(item.views)} />}
          <Fact label="Tipo" value={item.kind === 'song' ? 'Canción' : 'Vídeo'} />
        </dl>
        {item.in_library && <span className="badge">En tu biblioteca</span>}
      </div>
    </div>
  )
}

function PlaylistDetail({ id, onLoaded }: { id: string; onLoaded(p: PlaylistInfo): void }) {
  const client = useClient()
  const [info, setInfo] = useState<PlaylistInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const loaded = useRef(onLoaded)
  loaded.current = onLoaded
  useEffect(() => {
    client
      .getPlaylist(id)
      .then((p) => {
        setInfo(p)
        loaded.current(p)
      })
      .catch((e) => setError(e.message))
  }, [client, id])
  if (error) return <p className="sheet-text">{error}</p>
  if (!info) return <p className="sheet-text">Cargando canciones…</p>
  return (
    <ol className="track-list">
      {info.tracks.map((t, i) => (
        <li key={`${t.id}-${i}`}>
          <span className="track-n tabular">{i + 1}</span>
          <span className="track-title">
            {t.title}
            <small>{t.artist}</small>
          </span>
          {t.in_library && <span className="badge">En tu biblioteca</span>}
          <span className="tabular track-dur">{t.duration_s != null ? formatDuration(t.duration_s) : ''}</span>
        </li>
      ))}
    </ol>
  )
}

export function TrackDetailSheet({ item, options, onOptions, onDownload, onDownloadPlaylist, onClose }: Props) {
  const [count, setCount] = useState<number | null>(null)
  const isPlaylist = item.kind === 'playlist'
  return (
    <GlassSheet
      title={isPlaylist ? item.title : 'Detalles'}
      onClose={onClose}
      wide={isPlaylist}
      actions={
        isPlaylist ? (
          <DownloadButton
            options={options}
            onOptions={onOptions}
            label={count != null ? `Descargar playlist (${count})` : 'Descargar playlist'}
            busy={count == null || count === 0}
            onDownload={() => count && onDownloadPlaylist(item.id, count)}
          />
        ) : (
          <DownloadButton options={options} onOptions={onOptions} onDownload={() => onDownload(item)} />
        )
      }
    >
      {isPlaylist ? <PlaylistDetail id={item.id} onLoaded={(p) => setCount(p.tracks.length)} /> : <SongDetail item={item} />}
    </GlassSheet>
  )
}
