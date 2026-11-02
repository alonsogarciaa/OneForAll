import { useEffect, useState, type ReactNode } from 'react'
import { FolderOpen, RefreshCw } from 'lucide-react'
import { useClient } from '../lib/engine'
import { useUiStore } from '../stores/uiStore'
import { FORMAT_NAMES, MP3_QUALITIES } from '../lib/format'
import type { FormatId, Settings } from '../lib/types'
import './settings.css'

const SAMPLE = { artist: 'Quevedo', title: 'La Graciosa', album: 'El Baifo' }
const EXT: Record<FormatId, string> = { mp3: 'mp3', aac: 'm4a', alac: 'm4a', opus: 'opus', ogg: 'ogg', flac: 'flac', wav: 'wav', aiff: 'aiff', original: 'webm' }

export function previewName(template: string, format: FormatId): string {
  const name = template
    .replace(/\{(\w+)\}/g, (_, k: string) => (SAMPLE as Record<string, string>)[k] ?? '')
    .replace(/^[\s\-–_·|,]+|[\s\-–_·|,]+$/g, '')
    .replace(/[<>:"/\\|?*]/g, '')
    .trim()
  return `${name || 'Sin título'}.${EXT[format]}`
}

function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="setting-row">
      <div>
        <div className="setting-label">{label}</div>
        {hint && <div className="setting-hint">{hint}</div>}
      </div>
      <div className="setting-control">{children}</div>
    </div>
  )
}

export function SettingsScreen() {
  const client = useClient()
  const ui = useUiStore()
  const [s, setS] = useState<Settings | null>(null)
  const [ytdlp, setYtdlp] = useState<{ busy: boolean; text: string | null }>({ busy: false, text: null })
  const [range, setRange] = useState<{ min: string; max: string } | null>(null)

  useEffect(() => {
    client
      .getSettings()
      .then((v) => {
        setS(v)
        setRange({ min: String(v.bpm_min), max: String(v.bpm_max) })
      })
      .catch((e) => ui.toast(e.message, 'error'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client])

  // Every change is saved right away.
  const save = (patch: Partial<Settings>) => {
    if (!s) return
    const next = { ...s, ...patch }
    setS(next)
    client.putSettings(next).catch((e) => ui.toast(e.message, 'error'))
  }

  const updateYtdlp = async () => {
    setYtdlp({ busy: true, text: null })
    try {
      const r = await client.updateYtdlp()
      setYtdlp({ busy: false, text: r.output.trim().split('\n').pop() || (r.ok ? 'Actualizado' : 'No se pudo actualizar') })
    } catch (e: any) {
      setYtdlp({ busy: false, text: e.message })
    }
  }

  const rangeError = (() => {
    if (!range) return null
    const lo = Number(range.min)
    const hi = Number(range.max)
    if (!Number.isFinite(lo) || !Number.isFinite(hi) || lo < 40 || hi > 250) return 'Usa valores entre 40 y 250'
    if (lo >= hi) return 'El mínimo debe ser menor que el máximo'
    return null
  })()

  const changeRange = (next: { min: string; max: string }) => {
    setRange(next)
    const lo = Number(next.min)
    const hi = Number(next.max)
    if (Number.isFinite(lo) && Number.isFinite(hi) && lo >= 40 && hi <= 250 && lo < hi) save({ bpm_min: lo, bpm_max: hi })
  }

  if (!s) return <h1 className="screen-title">Ajustes</h1>

  return (
    <section className="settings">
      <h1 className="screen-title">Ajustes</h1>

      <h2 className="settings-group">Descargas</h2>
      <div className="settings-card">
        <Row label="Carpeta de música" hint={s.music_dir}>
          <button
            className="btn btn-sm"
            onClick={async () => {
              const dir = await window.oneforall.pickFolder()
              if (dir) save({ music_dir: dir })
            }}
          >
            Cambiar…
          </button>
        </Row>
        <Row label="Formato por defecto">
          <select
            className="field"
            aria-label="Formato por defecto"
            value={s.default_format}
            onChange={(e) => save({ default_format: e.target.value as FormatId })}
          >
            {(Object.keys(FORMAT_NAMES) as FormatId[]).map((f) => (
              <option key={f} value={f}>
                {f === 'original' ? 'Original (sin convertir)' : FORMAT_NAMES[f]}
              </option>
            ))}
          </select>
          {s.default_format === 'mp3' && (
            <select className="field" aria-label="Calidad por defecto" value={s.default_quality} onChange={(e) => save({ default_quality: e.target.value })}>
              {MP3_QUALITIES.map((q) => (
                <option key={q} value={q}>
                  {q === 'v0' ? 'VBR V0' : `${q} kbps`}
                </option>
              ))}
            </select>
          )}
        </Row>
        <Row label="Nombre de archivo">
          <input
            className="field template-field"
            aria-label="Plantilla de nombre"
            value={s.name_template}
            spellCheck={false}
            onChange={(e) => save({ name_template: e.target.value })}
          />
        </Row>
        <p className="settings-note">
          Usa <code>{'{artist}'}</code>, <code>{'{title}'}</code> y <code>{'{album}'}</code>. Ejemplo: <strong>{previewName(s.name_template, s.default_format)}</strong>
        </p>
        <Row label="Descargas a la vez">
          <select
            className="field"
            aria-label="Descargas a la vez"
            value={s.download_concurrency}
            onChange={(e) => save({ download_concurrency: Number(e.target.value) })}
          >
            {[1, 2, 3, 4, 5, 6].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </Row>
      </div>

      <h2 className="settings-group">Análisis</h2>
      <div className="settings-card">
        <Row label="Analizar al descargar" hint="Calcula BPM, tonalidad y volumen de cada canción descargada.">
          <button
            role="switch"
            aria-checked={s.analyze_on_download}
            aria-label="Analizar al descargar"
            className="switch"
            onClick={() => save({ analyze_on_download: !s.analyze_on_download })}
          >
            <span />
          </button>
        </Row>
        <Row label="Tonalidad en las etiquetas" hint="Cómo se escribe en el archivo para Rekordbox, Serato, VirtualDJ o Traktor.">
          <div className="segmented" role="group" aria-label="Notación de tonalidad en etiquetas">
            <button aria-pressed={s.key_notation === 'camelot'} onClick={() => save({ key_notation: 'camelot' })}>
              Camelot
            </button>
            <button aria-pressed={s.key_notation === 'musical'} onClick={() => save({ key_notation: 'musical' })}>
              Musical
            </button>
          </div>
        </Row>
        <Row label="Rango de BPM" hint={rangeError ?? 'Los tempos fuera del rango se doblan o se dividen (64 → 128).'}>
          <input
            className="field bpm-field"
            aria-label="BPM mínimo"
            inputMode="numeric"
            value={range?.min ?? ''}
            onChange={(e) => changeRange({ min: e.target.value, max: range?.max ?? '' })}
          />
          <span className="range-dash">–</span>
          <input
            className="field bpm-field"
            aria-label="BPM máximo"
            inputMode="numeric"
            value={range?.max ?? ''}
            onChange={(e) => changeRange({ min: range?.min ?? '', max: e.target.value })}
          />
        </Row>
      </div>

      <h2 className="settings-group">Apariencia</h2>
      <div className="settings-card">
        <Row label="Tema">
          <div className="segmented" role="group" aria-label="Tema">
            <button aria-pressed={ui.theme === 'dark'} onClick={() => ui.setTheme('dark')}>
              Oscuro
            </button>
            <button aria-pressed={ui.theme === 'light'} onClick={() => ui.setTheme('light')}>
              Claro
            </button>
          </div>
        </Row>
        <Row label="Modo tintado" hint="Hace el cristal más opaco para leer mejor.">
          <button
            role="switch"
            aria-checked={s.tinted}
            aria-label="Modo tintado"
            className="switch"
            onClick={() => {
              ui.setTinted(!s.tinted)
              save({ tinted: !s.tinted })
            }}
          >
            <span />
          </button>
        </Row>
      </div>

      <h2 className="settings-group">Mantenimiento</h2>
      <div className="settings-card">
        <Row label="yt-dlp" hint={ytdlp.text ?? 'Si las descargas empiezan a fallar, actualízalo.'}>
          <button className="btn btn-sm" disabled={ytdlp.busy} onClick={updateYtdlp}>
            <RefreshCw size={14} className={ytdlp.busy ? 'spin' : undefined} />
            {ytdlp.busy ? 'Actualizando…' : 'Actualizar yt-dlp'}
          </button>
        </Row>
        <Row label="Registros" hint="Útiles si algo falla y quieres revisarlo.">
          <button
            className="btn btn-sm"
            onClick={() => client.info().then((i) => window.oneforall.openPath(i.logs_dir)).catch((e) => ui.toast(e.message, 'error'))}
          >
            <FolderOpen size={14} />
            Abrir carpeta de logs
          </button>
        </Row>
      </div>

      <h2 className="settings-group">Acerca de</h2>
      <div className="settings-card">
        <p className="settings-about">
          La tonalidad se detecta con el modelo CNN de madmom (Korzeniowski y Widmer), con licencia CC BY-NC-SA 4.0:
          solo uso personal, no comercial. El tempo usa DeepRhythm (AGPL-3.0). Más detalles en el README del proyecto.
        </p>
      </div>
    </section>
  )
}
