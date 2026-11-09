// Mirrors of the engine's JSON shapes (engine/djengine).

export type Kind = 'song' | 'video' | 'playlist' | 'soundcloud'
export type SearchKind = 'songs' | 'videos' | 'playlists' | 'soundcloud'

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
  source?: 'youtube' | 'soundcloud'
  preview_only?: boolean
}

/** A recommendation: a search result plus what the quick analysis already knows. */
export interface Rec extends SearchResult {
  bpm: number | null
  camelot: string | null
  analysed: boolean
}

export interface MoodSection {
  title: string
  items: { title: string; params: string }[]
}

export interface ImportItem {
  title: string
  artist: string
  duration_s: number | null
  url?: string | null
  id?: string | null
}

export interface ImportList {
  name: string
  service: 'spotify' | 'apple' | 'soundcloud'
  items: ImportItem[]
  truncated: boolean
}

export interface MatchResult {
  status: 'found' | 'review' | 'missing'
  best: SearchResult | null
  alternatives: SearchResult[]
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
  lufs?: number | null
  analyzed_at?: string | null
  has_stems?: boolean
  enhanced?: boolean
  origin_video_id?: string | null
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
  bpm?: number | null
  camelot?: string | null
  path?: string | null
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'

export interface Job {
  id: string
  type: 'download' | 'convert' | 'playlist' | 'analysis' | 'stems'
  title: string
  status: JobStatus
  stage: string
  pct: number
  parent_id: string | null
  error: { code: string; message: string } | null
  result: Record<string, any> | null
  children: string[]
  /** Original request, used for "Reintentar". */
  payload?: Record<string, any> | null
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
  then_stems?: { stems: string[]; karaoke: boolean } | null
}

export interface Settings {
  music_dir: string
  default_format: FormatId
  default_quality: string
  name_template: string
  download_concurrency: number
  tinted: boolean
  analyze_on_download: boolean
  key_notation: 'camelot' | 'musical'
  bpm_min: number
  bpm_max: number
  stems_dir: string | null
  stems_format: 'wav16' | 'wav24' | 'flac' | 'mp3'
  stems_backend: 'auto' | 'cpu'
  videos_dir?: string | null
  enhance_on_download?: boolean
  enhance_mode?: 'copy' | 'replace'
  enhance_format?: 'same' | 'flac'
}

export interface AnalysisRecord {
  path: string
  bpm: number | null
  bpm_confidence: number | null
  bpm_source: 'auto' | 'manual'
  tonic: string | null
  mode: 'major' | 'minor' | null
  camelot: string | null
  key_confidence: number | null
  lufs: number | null
  peak_db: number | null
  version: number
  created_at: string
}

export interface Grid {
  anchor: number
  bpm: number
  source: 'auto' | 'manual'
  meter: number
}

export type GridOp = { anchor?: number; bpm?: number; shift_ms?: number; shift_beats?: number; scale?: 0.5 | 2; reset?: boolean }

export type SectionLabel = 'Intro' | 'Verso' | 'Subida' | 'Estribillo/Drop' | 'Bajón' | 'Outro'

export interface Section {
  start: number
  end: number
  label: SectionLabel
  source?: 'auto' | 'manual'
}

export interface AnalysisSidecar {
  beats: number[]
  waveform: { peaks: number[]; low: number[]; mid: number[]; high: number[] }
  duration: number
  grid?: Grid
  sections?: Section[]
  sections_auto?: Section[]
  needs_reanalysis?: boolean
}

export interface HarmonicRow {
  track: TrackRecord
  level: 'same' | 'adjacent' | 'relative'
  bpm_diff_pct: number
}

export type EngineEvent =
  | { type: 'engine.hello' }
  | { type: 'job.queued' | 'job.done' | 'job.failed' | 'job.cancelled'; job: Job }
  | { type: 'job.progress'; job: Job; speed?: string | null; eta?: string | null }
  | { type: 'quick.result'; video_id: string; bpm: number | null; camelot: string | null; failed: boolean }
  | { type: 'match.result'; job_id: string; index: number; result: MatchResult }

export const FINAL_STATUSES: JobStatus[] = ['done', 'failed', 'cancelled']
