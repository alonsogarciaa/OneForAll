import { ListMusic, Music2 } from 'lucide-react'
import { DownloadButton } from './DownloadButton'
import { formatDuration, formatViews } from '../lib/format'
import type { ConvertOptions, SearchResult } from '../lib/types'

interface Props {
  item: SearchResult
  options: ConvertOptions
  onOptions(o: ConvertOptions): void
  onDownload(item: SearchResult): void
  onOpen(item: SearchResult): void
  onStems?(item: SearchResult, stems: string[] | null): void
}

export function Cover({ src, size = 48, playlist = false }: { src: string | null; size?: number; playlist?: boolean }) {
  return (
    <div className="cover" style={{ width: size, height: size }}>
      {src ? <img src={src} alt="" loading="lazy" referrerPolicy="no-referrer" /> : playlist ? <ListMusic size={size / 2.4} /> : <Music2 size={size / 2.4} />}
    </div>
  )
}

export function ResultRow({ item, options, onOptions, onDownload, onOpen, onStems }: Props) {
  const isPlaylist = item.kind === 'playlist'
  const sub = [item.artist, item.album].filter(Boolean).join(' · ')
  return (
    <div
      className="result-row"
      data-row
      role="button"
      tabIndex={0}
      onClick={() => onOpen(item)}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget && onOpen(item)}
    >
      <Cover src={item.thumbnail} playlist={isPlaylist} />
      <div className="result-main">
        <div className="result-title">
          <span>{item.title}</span>
          {item.in_library && <span className="badge">En tu biblioteca</span>}
        </div>
        <div className="result-sub">{sub}</div>
      </div>
      <div className="result-meta tabular">
        {isPlaylist ? (
          item.track_count != null && <span>{item.track_count} canciones</span>
        ) : (
          <>
            {item.views != null && <span title="Visualizaciones">{formatViews(item.views)}</span>}
            {item.duration_s != null && <span className="result-duration">{formatDuration(item.duration_s)}</span>}
          </>
        )}
      </div>
      {isPlaylist ? (
        <button className="btn btn-sm" onClick={(e) => (e.stopPropagation(), onOpen(item))}>
          Ver playlist
        </button>
      ) : (
        <DownloadButton
          variant="subtle"
          options={options}
          onOptions={onOptions}
          onDownload={() => onDownload(item)}
          onStems={onStems && ((stems) => onStems(item, stems))}
        />
      )}
    </div>
  )
}
