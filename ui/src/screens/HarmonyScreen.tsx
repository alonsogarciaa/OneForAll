import { useEffect, useMemo, useState } from 'react'
import { Disc3, SearchX } from 'lucide-react'
import { KeyChip } from '../components/KeyChip'
import { useClient } from '../lib/engine'
import { CAMELOT_CODES, compatLabel, displayKey } from '../lib/camelot'
import { useUiStore } from '../stores/uiStore'
import type { HarmonicRow, TrackRecord } from '../lib/types'
import './harmony.css'

const TOLERANCES = [2, 4, 6, 8]

function pct(v: number): string {
  const s = Math.abs(v).toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${s} %`
}

export function HarmonyScreen() {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const openData = useUiStore((s) => s.openData)
  const [tracks, setTracks] = useState<TrackRecord[] | null>(null)
  const [mode, setMode] = useState<'track' | 'manual'>('track')
  const [ref, setRef] = useState<number | null>(null)
  const [bpm, setBpm] = useState('')
  const [camelot, setCamelot] = useState('')
  const [tol, setTol] = useState(6)
  const [rows, setRows] = useState<HarmonicRow[] | null>(null)

  useEffect(() => {
    client.library().then(setTracks).catch((e) => toast(e.message, 'error'))
  }, [client, toast])

  const analysed = useMemo(() => (tracks ?? []).filter((t) => t.bpm && t.camelot && !t.missing), [tracks])

  useEffect(() => {
    const params =
      mode === 'track'
        ? ref != null ? { ref_track: ref, bpm_tolerance: tol } : null
        : Number(bpm) > 0 && camelot ? { bpm: Number(bpm), camelot, bpm_tolerance: tol } : null
    if (!params) {
      setRows(null)
      return
    }
    let stale = false // a slower earlier answer must not overwrite the current one
    const t = setTimeout(() => {
      client
        .harmonic(params)
        .then((r) => !stale && setRows(r))
        .catch((e) => !stale && toast(e.message, 'error'))
    }, 150)
    return () => {
      stale = true
      clearTimeout(t)
    }
  }, [client, mode, ref, bpm, camelot, tol, toast])

  if (tracks && analysed.length === 0) {
    return (
      <section>
        <h1 className="screen-title">Armonía</h1>
        <div className="empty">
          <Disc3 size={40} strokeWidth={1.4} />
          <p>Analiza canciones de tu biblioteca para ver compatibles</p>
        </div>
      </section>
    )
  }

  return (
    <section className="harmony">
      <div className="screen-head">
        <h1 className="screen-title">Armonía</h1>
        <div className="segmented" role="group" aria-label="Referencia">
          <button aria-pressed={mode === 'track'} onClick={() => setMode('track')}>Pista</button>
          <button aria-pressed={mode === 'manual'} onClick={() => setMode('manual')}>Manual</button>
        </div>
      </div>

      <div className="harmony-controls">
        {mode === 'track' ? (
          <label className="format-field harmony-ref">
            <span>Pista de referencia</span>
            <select className="field" aria-label="Pista de referencia" value={ref ?? ''} onChange={(e) => setRef(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Elige una canción analizada…</option>
              {analysed.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title} — {t.artist} · {t.bpm!.toFixed(1)} BPM · {t.camelot}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <>
            <label className="format-field">
              <span>BPM</span>
              <input className="field harmony-bpm" aria-label="BPM de referencia" inputMode="decimal" value={bpm} onChange={(e) => setBpm(e.target.value.replace(',', '.'))} placeholder="128" />
            </label>
            <label className="format-field">
              <span>Tonalidad</span>
              <select className="field" aria-label="Tonalidad de referencia" value={camelot} onChange={(e) => setCamelot(e.target.value)}>
                <option value="">Elige…</option>
                {CAMELOT_CODES.map((c) => (
                  <option key={c} value={c}>{displayKey(c)}</option>
                ))}
              </select>
            </label>
          </>
        )}
        <div className="format-field">
          <span>Margen de BPM</span>
          <div className="segmented" role="group" aria-label="Margen de BPM">
            {TOLERANCES.map((v) => (
              <button key={v} aria-pressed={tol === v} onClick={() => setTol(v)}>±{v} %</button>
            ))}
          </div>
        </div>
      </div>

      {rows && rows.length === 0 && (
        <div className="empty">
          <SearchX size={40} strokeWidth={1.4} />
          <p>No hay pistas compatibles con estos criterios</p>
        </div>
      )}
      {rows && rows.length > 0 && (
        <ul className="harmonic-list">
          {rows.map((r) => (
            <li key={r.track.id} data-testid="harmonic-row" onDoubleClick={() => openData(r.track.path)} title="Doble clic para ver sus datos">
              <KeyChip camelot={r.track.camelot} />
              <span className="harmonic-title">
                <span className="cell-strong">{r.track.title}</span>
                <small>{r.track.artist}</small>
              </span>
              <span className="tabular harmonic-bpm">{r.track.bpm!.toFixed(1)} BPM</span>
              <span className="tabular harmonic-diff">{pct(r.bpm_diff_pct)}</span>
              <span className={`badge level-${r.level}`}>{compatLabel(r.level)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
