import { useEffect, useRef } from 'react'
import type { AnalysisSidecar } from '../lib/types'

interface Props {
  data: AnalysisSidecar['waveform']
  beats: number[]
  duration: number
  position: number
  onSeek(seconds: number): void
  /** Mixer only: loop region drawn on the wave, set by dragging (a drag under MIN_LOOP_S is a seek). */
  loop?: { start: number; end: number } | null
  onLoop?(start: number, end: number): void
  /** Beat times the loop edges snap to (Alt held: no snapping). */
  snap?: number[]
}

const MIN_LOOP_S = 0.25
const EDGE_PX = 6

function nearest(t: number, snap: number[] | undefined): number {
  if (!snap || snap.length === 0) return t
  return snap.reduce((best, b) => (Math.abs(b - t) < Math.abs(best - t) ? b : best), snap[0])
}

// Band colours (Rekordbox-like): bass red, mids green, highs blue, blended by energy.
const LOW = [255, 69, 58]
const MID = [52, 199, 89]
const HIGH = [90, 200, 250]

function mix(l: number, m: number, h: number): string {
  const sum = l + m + h || 1
  const c = [0, 1, 2].map((i) => Math.round((LOW[i] * l + MID[i] * m + HIGH[i] * h) / sum))
  return `rgb(${c[0]},${c[1]},${c[2]})`
}

export function Waveform({ data, beats, duration, position, onSeek, loop = null, onLoop, snap }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const drag = useRef<{ t0: number; anchor: number | null } | null>(null)

  useEffect(() => {
    const el = canvas.current
    if (!el) return
    const draw = () => {
      const ctx = el.getContext('2d')
      if (!ctx) return // jsdom / no canvas support
      const dpr = window.devicePixelRatio || 1
      const w = el.clientWidth
      const h = el.clientHeight
      el.width = Math.round(w * dpr)
      el.height = Math.round(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)
      const n = data.peaks.length
      const mid = h / 2
      const step = n / w
      for (let x = 0; x < w; x++) {
        const i = Math.min(n - 1, Math.floor(x * step))
        const amp = data.peaks[i] * (mid - 2)
        ctx.globalAlpha = x / w <= position / (duration || 1) ? 1 : 0.55
        ctx.fillStyle = mix(data.low[i], data.mid[i], data.high[i])
        ctx.fillRect(x, mid - amp, 1, Math.max(1, amp * 2))
      }
      ctx.globalAlpha = 1
      if (duration > 0 && loop) {
        const x0 = (loop.start / duration) * w
        const x1 = (loop.end / duration) * w
        ctx.fillStyle = 'rgba(10,132,255,0.18)'
        ctx.fillRect(x0, 0, x1 - x0, h)
        ctx.fillStyle = 'rgba(10,132,255,0.9)'
        ctx.fillRect(x0 - 1, 0, 2, h)
        ctx.fillRect(x1 - 1, 0, 2, h)
      }
      if (duration > 0) {
        // Bar lines (every 4th beat) faint and full height; single beats only as short ticks when there is room.
        const spacing = beats.length > 1 ? ((beats[1] - beats[0]) / duration) * w : 0
        beats.forEach((b, k) => {
          const bar = k % 4 === 0
          if (!bar && spacing < 5) return
          if (bar && spacing * 4 < 5) return
          const x = Math.round((b / duration) * w) + 0.5
          ctx.strokeStyle = bar ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.35)'
          ctx.beginPath()
          ctx.moveTo(x, bar ? 0 : h - 6)
          ctx.lineTo(x, h)
          ctx.stroke()
        })
        const px = Math.round((position / duration) * w) + 0.5
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.moveTo(px, 0)
        ctx.lineTo(px, h)
        ctx.stroke()
        ctx.lineWidth = 1
      }
    }
    draw()
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(draw) : null
    ro?.observe(el)
    return () => ro?.disconnect()
  }, [data, beats, duration, position, loop])

  return (
    <canvas
      ref={canvas}
      className="waveform"
      role="slider"
      aria-label="Posición de reproducción"
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      aria-valuenow={Math.round(position)}
      tabIndex={0}
      onClick={
        onLoop
          ? undefined
          : (e) => {
              const r = e.currentTarget.getBoundingClientRect()
              onSeek(((e.clientX - r.left) / r.width) * duration)
            }
      }
      onMouseDown={
        onLoop &&
        ((e) => {
          const r = e.currentTarget.getBoundingClientRect()
          const t = ((e.clientX - r.left) / r.width) * duration
          const px = (x: number) => (x / duration) * r.width
          // grabbing an edge of the current loop moves that edge; the other one stays put
          let anchor: number | null = null
          if (loop && Math.abs(px(t) - px(loop.start)) <= EDGE_PX) anchor = loop.end
          else if (loop && Math.abs(px(t) - px(loop.end)) <= EDGE_PX) anchor = loop.start
          drag.current = { t0: t, anchor }
        })
      }
      onMouseUp={
        onLoop &&
        ((e) => {
          const d = drag.current
          drag.current = null
          if (!d) return
          const r = e.currentTarget.getBoundingClientRect()
          const t1 = Math.max(0, Math.min(duration, ((e.clientX - r.left) / r.width) * duration))
          const from = d.anchor ?? d.t0
          if (d.anchor === null && Math.abs(t1 - d.t0) < MIN_LOOP_S) {
            onSeek(Math.round(t1 * 1000) / 1000)
            return
          }
          const s = e.altKey ? undefined : snap
          const ms = (x: number) => Math.round(x * 1000) / 1000
          const a = ms(nearest(Math.min(from, t1), s))
          const b = ms(nearest(Math.max(from, t1), s))
          if (b - a >= MIN_LOOP_S) onLoop(a, b)
        })
      }
      onKeyDown={(e) => {
        if (e.key === 'ArrowRight') onSeek(Math.min(duration, position + 5))
        if (e.key === 'ArrowLeft') onSeek(Math.max(0, position - 5))
      }}
    />
  )
}
