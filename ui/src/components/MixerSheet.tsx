import { useCallback, useEffect, useRef, useState } from 'react'
import { Pause, Play, Repeat, SkipBack } from 'lucide-react'
import { GlassSheet } from './GlassSheet'
import { Waveform } from './Waveform'
import { useClient } from '../lib/engine'
import { camelotShift } from '../lib/camelot'
import { formatDuration } from '../lib/format'
import { STEM_LABEL } from '../lib/stems'
import { useUiStore } from '../stores/uiStore'
import { createAudioContext, decodeStem, MixerEngine } from '../mixer/engine'
import { Metronome } from '../mixer/metronome'
import { createStretch } from '../mixer/stretch'
import { defaultState, mixerStems, parseState, stemState, MIXER_MAX_SECONDS, type MixState, type StemState } from '../mixer/mixState'
import type { AnalysisSidecar } from '../lib/types'
import './mixer.css'

type Phase =
  | { kind: 'loading'; done: number; total: number }
  | { kind: 'ready' }
  | { kind: 'error'; message: string; reseparate?: boolean }

interface Analysis {
  bpm: number | null
  camelot: string | null
  beats: number[]
}

const SPEEDS = [0.5, 0.75, 0.9, 1]
const SAVE_MS = 500
const MISSING = 'Faltan stems de esta canción'
const TOO_LONG = 'Pista demasiado larga para el mezclador'
const NO_MEMORY = 'No hay memoria suficiente para el mezclador'

class MissingStem extends Error {}

const comma = (n: number, d = 1) => n.toFixed(d).replace('.', ',')
const baseName = (p: string) => p.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') ?? p

/** Waveform for tracks never analysed: peaks of the summed stems (all bands equal). */
function peaksFrom(stems: { channels: Float32Array[] }[], n = 2000): AnalysisSidecar['waveform'] {
  const len = Math.min(...stems.map((s) => s.channels[0].length))
  const size = Math.max(1, Math.ceil(len / n))
  const peaks: number[] = []
  for (let b = 0; b < n && b * size < len; b++) {
    let max = 0
    for (let i = b * size; i < Math.min(len, (b + 1) * size); i++) {
      let sum = 0
      for (const s of stems) sum += s.channels[0][i]
      max = Math.max(max, Math.abs(sum))
    }
    peaks.push(max)
  }
  const top = Math.max(...peaks, 1e-9)
  const norm = peaks.map((p) => p / top)
  return { peaks: norm, low: norm, mid: norm, high: norm }
}

function typing(el: EventTarget | null): boolean {
  const e = el as HTMLElement | null
  return e != null && (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(e.tagName) || e.isContentEditable)
}

export function MixerSheet({ path, onClose }: { path: string; onClose(): void }) {
  const client = useClient()
  const openStems = useUiStore((s) => s.openStems)
  const [phase, setPhase] = useState<Phase>({ kind: 'loading', done: 0, total: 0 })
  const [strips, setStrips] = useState<string[]>([])
  const [state, setState] = useState<MixState>(defaultState)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [wave, setWave] = useState<AnalysisSidecar['waveform'] | null>(null)
  const [duration, setDuration] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [pos, setPos] = useState(0)
  const engine = useRef<MixerEngine | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const metro = useRef<Metronome | null>(null)
  const stateRef = useRef(state)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let cancelled = false
    const ctx = createAudioContext()
    const eng = new MixerEngine(ctx, createStretch)
    ctxRef.current = ctx
    engine.current = eng
    metro.current = new Metronome(ctx, eng)
    ;(async () => {
      try {
        const [st, an, saved] = await Promise.all([
          client.getStems(path),
          client.getAnalysis(path).catch((e: any) => (e?.status === 404 ? null : Promise.reject(e))),
          client.getMixerState(path).catch(() => ({ state: null }))
        ])
        if (cancelled) return
        const list = mixerStems(st.stems)
        if (list.length < 2) throw new MissingStem()
        if (an && an.sidecar.duration > MIXER_MAX_SECONDS) {
          setPhase({ kind: 'error', message: TOO_LONG })
          return
        }
        setPhase({ kind: 'loading', done: 0, total: list.length })
        const decoded: { stem: string; channels: Float32Array[] }[] = []
        for (const [i, s] of list.entries()) {
          const r = await fetch(client.audioUrl(s.file))
          if (!r.ok) throw new MissingStem()
          const channels = await decodeStem(ctx, await r.arrayBuffer())
          if (cancelled) return
          if (channels[0].length / ctx.sampleRate > MIXER_MAX_SECONDS) {
            setPhase({ kind: 'error', message: TOO_LONG })
            return
          }
          decoded.push({ stem: s.stem, channels })
          setPhase({ kind: 'loading', done: i + 1, total: list.length })
        }
        const wf = an ? an.sidecar.waveform : peaksFrom(decoded)
        await eng.load(decoded)
        decoded.length = 0 // the nodes hold their own copy: let the decoded audio go
        if (cancelled) return
        const init = parseState(saved.state)
        stateRef.current = init
        eng.apply(init)
        setState(init)
        setStrips(list.map((s) => s.stem))
        setAnalysis(an ? { bpm: an.record.bpm, camelot: an.record.camelot, beats: an.sidecar.beats } : null)
        setWave(wf)
        setDuration(eng.duration || an?.sidecar.duration || 0)
        setPhase({ kind: 'ready' })
      } catch (e: any) {
        if (cancelled) return
        if (e instanceof MissingStem) setPhase({ kind: 'error', message: MISSING, reseparate: true })
        else if (e instanceof RangeError || e?.name === 'QuotaExceededError') setPhase({ kind: 'error', message: NO_MEMORY })
        else setPhase({ kind: 'error', message: e?.message || 'No se pudo abrir el mezclador' })
      }
    })()
    return () => {
      cancelled = true
      metro.current?.stop()
      if (saveTimer.current) clearTimeout(saveTimer.current)
      void eng.dispose()
    }
  }, [client, path])

  const update = useCallback(
    (fn: (s: MixState) => MixState) => {
      const next = fn(stateRef.current)
      stateRef.current = next
      setState(next)
      engine.current?.apply(next)
      if (saveTimer.current) clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(() => void client.putMixerState(path, next).catch(() => undefined), SAVE_MS)
    },
    [client, path]
  )

  const setStem = (stem: string, patch: Partial<StemState>) =>
    update((s) => ({ ...s, stems: { ...s.stems, [stem]: { ...stemState(s, stem), ...patch } } }))

  const bpm = analysis?.bpm ?? null

  const togglePlay = useCallback(async () => {
    const eng = engine.current
    const ctx = ctxRef.current
    if (!eng || !ctx) return
    if (eng.playing) {
      eng.pause()
      metro.current?.stop()
      setPlaying(false)
      return
    }
    if (ctx.state === 'suspended') await ctx.resume()
    eng.play()
    const m = stateRef.current.metronome
    if (m.on && bpm) metro.current?.start(m, analysis?.beats ?? null, bpm)
    setPlaying(true)
  }, [analysis, bpm])

  // position readout while playing
  useEffect(() => {
    if (!playing) return
    const t = setInterval(() => setPos(engine.current?.position() ?? 0), 50)
    return () => clearInterval(t)
  }, [playing])

  useEffect(() => {
    if (phase.kind !== 'ready') return
    const onKey = (e: KeyboardEvent) => {
      if (typing(e.target)) return
      if (e.code === 'Space') {
        e.preventDefault()
        if (!e.repeat) void togglePlay()
      } else if (e.code === 'KeyL' && stateRef.current.loop) {
        update((s) => ({ ...s, loop_on: !s.loop_on }))
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [phase.kind, togglePlay, update])

  const seek = (t: number) => {
    engine.current?.seek(t)
    setPos(t)
  }

  const toggleMetronome = () =>
    update((s) => {
      const on = !s.metronome.on
      if (engine.current?.playing && bpm) {
        if (on) metro.current?.start(s.metronome, analysis?.beats ?? null, bpm)
        else metro.current?.stop()
      }
      return { ...s, metronome: { ...s.metronome, on } }
    })

  const title = `Mezclador · ${baseName(path)}`

  if (phase.kind === 'error') {
    return (
      <GlassSheet title={title} onClose={onClose} wide>
        <div className="mixer-error">
          <p>{phase.message}</p>
          {phase.reseparate && (
            <button
              className="btn btn-primary"
              onClick={() => {
                openStems([path])
                onClose()
              }}
            >
              Separar de nuevo
            </button>
          )}
        </div>
      </GlassSheet>
    )
  }

  if (phase.kind === 'loading') {
    return (
      <GlassSheet title={title} onClose={onClose} wide>
        <div className="mixer-loading">
          <span>{phase.total ? `Cargando stems… ${phase.done}/${phase.total}` : 'Cargando stems…'}</span>
          <div className="progress">
            <div style={{ width: `${phase.total ? (phase.done / phase.total) * 100 : 0}%` }} />
          </div>
        </div>
      </GlassSheet>
    )
  }

  const camelot = analysis?.camelot ?? null
  const loopStart = state.loop_on && state.loop ? state.loop.start : 0

  return (
    <GlassSheet title={title} onClose={onClose} full>
      <div className="mixer">
        <section className="mixer-transport">
          <button className="btn btn-primary icon-btn mixer-play" aria-label={playing ? 'Pausar' : 'Reproducir'} onClick={() => void togglePlay()}>
            {playing ? <Pause size={18} /> : <Play size={18} />}
          </button>
          <button className="btn btn-ghost icon-btn" aria-label="Al inicio" onClick={() => seek(loopStart)}>
            <SkipBack size={16} />
          </button>
          <span className="tabular mixer-time">
            {formatDuration(pos)} / {formatDuration(duration)}
          </span>
          <button
            className="btn btn-sm"
            aria-pressed={state.loop_on}
            disabled={!state.loop}
            onClick={() => update((s) => ({ ...s, loop_on: !s.loop_on }))}
            title="Arrastra sobre la onda para marcar un bucle (L)"
          >
            <Repeat size={14} />
            Bucle
          </button>
        </section>

        {wave && (
          <Waveform
            data={wave}
            beats={analysis?.beats ?? []}
            duration={duration}
            position={pos}
            onSeek={seek}
            loop={state.loop}
            onLoop={(start, end) => update((s) => ({ ...s, loop: { start, end }, loop_on: true }))}
            snap={analysis?.beats}
          />
        )}

        <section className="mixer-globals">
          <div className="mixer-control">
            <span className="ds-label">Velocidad</span>
            <input
              type="range"
              min={0.5}
              max={1}
              step={0.01}
              value={state.rate}
              aria-label="Velocidad"
              onChange={(e) => update((s) => ({ ...s, rate: Number(e.target.value) }))}
            />
            <div className="segmented">
              {SPEEDS.map((v) => (
                <button key={v} aria-pressed={state.rate === v} onClick={() => update((s) => ({ ...s, rate: v }))}>
                  {`${comma(v, v === 0.75 ? 2 : 1)}×`}
                </button>
              ))}
            </div>
            <span className="ds-sub tabular">
              {bpm ? `BPM ${comma(bpm)} → ${comma(bpm * state.rate)}` : `${Math.round(state.rate * 100)} %`}
            </span>
          </div>
          <div className="mixer-control">
            <span className="ds-label">Tonalidad</span>
            <div className="mixer-stepper">
              <button className="btn btn-sm" aria-label="Bajar tono" disabled={state.semis <= -12} onClick={() => update((s) => ({ ...s, semis: s.semis - 1 }))}>
                −
              </button>
              <span className="tabular">{state.semis > 0 ? `+${state.semis}` : state.semis}</span>
              <button className="btn btn-sm" aria-label="Subir tono" disabled={state.semis >= 12} onClick={() => update((s) => ({ ...s, semis: s.semis + 1 }))}>
                +
              </button>
            </div>
            <span className="ds-sub tabular">{camelot ? `${camelot} → ${camelotShift(camelot, state.semis)}` : 'semitonos'}</span>
          </div>
          <div className="mixer-control">
            <span className="ds-label">Volumen general</span>
            <input
              type="range"
              min={0}
              max={150}
              value={Math.round(state.master * 100)}
              aria-label="Volumen general"
              onChange={(e) => update((s) => ({ ...s, master: Number(e.target.value) / 100 }))}
              onDoubleClick={() => update((s) => ({ ...s, master: 1 }))}
            />
          </div>
          <div className="mixer-control">
            <span className="ds-label">Metrónomo</span>
            <button className="btn btn-sm" aria-label="Metrónomo" aria-pressed={state.metronome.on} disabled={!bpm} onClick={toggleMetronome}>
              {state.metronome.on ? 'Activado' : 'Desactivado'}
            </button>
            {!bpm && <span className="ds-sub">Sin BPM</span>}
          </div>
        </section>

        <section className="mixer-strips">
          {strips.map((stem) => {
            const label = STEM_LABEL[stem] ?? stem
            const st = stemState(state, stem)
            return (
              <div key={stem} className={`mixer-strip stem-${stem}`}>
                <span className="strip-name" data-testid="strip-name">
                  {label}
                </span>
                <div className="strip-ms">
                  <button className="btn btn-sm strip-btn" aria-label={`Silenciar ${label}`} aria-pressed={st.mute} onClick={() => setStem(stem, { mute: !st.mute })}>
                    M
                  </button>
                  <button className="btn btn-sm strip-btn" aria-label={`Solo ${label}`} aria-pressed={st.solo} onClick={() => setStem(stem, { solo: !st.solo })}>
                    S
                  </button>
                </div>
                <input
                  type="range"
                  min={0}
                  max={150}
                  value={Math.round(st.gain * 100)}
                  aria-label={`Volumen ${label}`}
                  onChange={(e) => setStem(stem, { gain: Number(e.target.value) / 100 })}
                  onDoubleClick={() => setStem(stem, { gain: 1 })}
                />
                <div className="mixer-stepper">
                  <button className="btn btn-sm" aria-label={`Bajar tono ${label}`} disabled={st.semis <= -12} onClick={() => setStem(stem, { semis: st.semis - 1 })}>
                    −
                  </button>
                  <span className="tabular">{st.semis > 0 ? `+${st.semis}` : st.semis}</span>
                  <button className="btn btn-sm" aria-label={`Subir tono ${label}`} disabled={st.semis >= 12} onClick={() => setStem(stem, { semis: st.semis + 1 })}>
                    +
                  </button>
                </div>
              </div>
            )
          })}
        </section>
      </div>
    </GlassSheet>
  )
}
