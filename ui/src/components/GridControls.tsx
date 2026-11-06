import { useEffect, useRef, useState } from 'react'
import { useClient } from '../lib/engine'
import { useUiStore } from '../stores/uiStore'
import { createAudioContext } from '../mixer/engine'
import { Metronome } from '../mixer/metronome'
import type { Grid, GridOp } from '../lib/types'

const comma = (n: number) => n.toFixed(1).replace('.', ',')

function clock(s: number): string {
  const m = Math.floor(s / 60)
  const rest = s - m * 60
  return `${m}:${rest.toFixed(3).padStart(6, '0')}`
}

interface Props {
  path: string
  grid: Grid
  position: number
  /** The data sheet's player: the metronome follows its time. */
  audio: HTMLAudioElement | null
  onChange(grid: Grid): void
}

/** Beat grid editing: move the "1", nudge, halve/double, reset, and a metronome to check it by ear. */
export function GridControls({ path, grid, position, audio, onChange }: Props) {
  const client = useClient()
  const toast = useUiStore((s) => s.toast)
  const [metro, setMetro] = useState(false)
  const ctx = useRef<AudioContext | null>(null)

  const send = async (op: GridOp) => {
    try {
      const r = await client.putGrid(path, op)
      onChange(r.grid)
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  // clicks on the grid while the sheet's audio plays (song time read from the <audio> element)
  useEffect(() => {
    if (!metro || !grid.bpm) return
    const c = (ctx.current ??= createAudioContext())
    const songClock = {
      rate: 1,
      segments: (c0: number, c1: number) => {
        if (!audio || audio.paused) return []
        const s0 = audio.currentTime + (c0 - c.currentTime)
        return [{ song0: s0, song1: s0 + (c1 - c0), ctx0: c0 }]
      }
    }
    const met = new Metronome(c, songClock)
    const p = 60 / grid.bpm
    const first = grid.anchor - Math.floor(grid.anchor / p) * p
    const offset = Math.round((grid.anchor - first) / p) % 4 // the accent falls on the anchor's beat
    met.start({ meter: '4/4', offset, volume: 0.6 }, beatsFrom(first, p, 3600), grid.bpm)
    return () => met.silence()
  }, [metro, audio, grid.anchor, grid.bpm])

  useEffect(() => () => void ctx.current?.close?.(), [])

  return (
    <div className="ds-gridctl" aria-label="Rejilla">
      <span className="ds-sub tabular">{`${comma(grid.bpm)} BPM · 1 en ${clock(grid.anchor)}`}</span>
      <div className="ds-gridctl-row">
        <button className="btn btn-sm btn-primary" onClick={() => send({ anchor: Math.round(position * 1000) / 1000 })}>
          El 1 aquí
        </button>
        <button className="btn btn-sm" onClick={() => send({ shift_ms: -10 })}>−10 ms</button>
        <button className="btn btn-sm" onClick={() => send({ shift_ms: 10 })}>+10 ms</button>
        <button className="btn btn-sm" onClick={() => send({ shift_beats: -1 })}>−1 golpe</button>
        <button className="btn btn-sm" onClick={() => send({ shift_beats: 1 })}>+1 golpe</button>
        <button className="btn btn-sm" onClick={() => send({ scale: 0.5 })}>÷2</button>
        <button className="btn btn-sm" onClick={() => send({ scale: 2 })}>×2</button>
        <button className="btn btn-sm" aria-pressed={metro} onClick={() => setMetro((v) => !v)}>
          Metrónomo
        </button>
        <button className="btn btn-sm btn-ghost" onClick={() => send({ reset: true })}>
          Volver al automático
        </button>
      </div>
    </div>
  )
}

function beatsFrom(first: number, p: number, until: number): number[] {
  const out: number[] = []
  for (let t = first; t < until; t += p) out.push(Math.round(t * 10000) / 10000)
  return out
}
