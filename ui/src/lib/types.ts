// Mirrors of the engine's JSON shapes (engine/djengine).

export type Kind = 'song' | 'video' | 'playlist'
export type SearchKind = 'songs' | 'videos' | 'playlists'

export interface SearchResult {
  kind: Kind
  id: string
  title: string
  artist: string
  album: string
  duration_s: number | null
  views: number | null
  thumbnail: string | null
  url: string
  track_count: number | null
  in_library: boolean
}

export interface PlaylistInfo {
  id: string
  title: string
  tracks: SearchResult[]
}

export interface TrackRecord {
  id: number
  video_id: string | null
  title: string
  artist: string
  album: string
  duration_s: number | null
  views: number | null
  path: string
  format: string
  bitrate: number | null
  cover_path: string | null
  added_at: string
  bpm: number | null
  musical_key: string | null
  camelot: string | null
  missing: boolean
}

export interface HistoryEntry {
  id: number
  track_id: number | null
  video_id: string | null
  title: string
  artist: string
  action: 'download' | 'convert'
  status: 'done' | 'failed'
  at: string
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'

export interface Job {
  id: string
  type: 'download' | 'convert' | 'playlist'
  title: string
  status: JobStatus
  stage: string
  pct: number
  parent_id: string | null
  error: { code: string; message: string } | null
  result: Record<string, any> | null
  children: string[]
}

export type FormatId = 'mp3' | 'aac' | 'alac' | 'opus' | 'ogg' | 'flac' | 'wav' | 'aiff' | 'original'

export interface ConvertOptions {
  format: FormatId
  quality?: string | null
  sample_rate?: number | null
  bit_depth?: number | null
}

export interface DownloadRequest {
  target: SearchResult
  options: ConvertOptions
  force?: boolean
}

export interface Settings {
  music_dir: string
  default_format: FormatId
  default_quality: string
  name_template: string
  download_concurrency: number
  tinted: boolean
}

export type EngineEvent =
  | { type: 'engine.hello' }
  | { type: 'job.queued' | 'job.done' | 'job.failed' | 'job.cancelled'; job: Job }
  | { type: 'job.progress'; job: Job; speed?: string | null; eta?: string | null }

export const FINAL_STATUSES: JobStatus[] = ['done', 'failed', 'cancelled']
