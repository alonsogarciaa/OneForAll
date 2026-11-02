import { useEffect, useRef } from 'react'
import type { AnalysisSidecar } from '../lib/types'

interface Props {
  data: AnalysisSidecar['waveform']
  beats: number[]
  duration: number
  position: number
  onSeek(seconds: number): void
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

export function Waveform({ data, beats, duration, position, onSeek }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null)

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
  }, [data, beats, duration, position])

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
      onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect()
        onSeek(((e.clientX - r.left) / r.width) * duration)
      }}
      onKeyDown={(e) => {
        if (e.key === 'ArrowRight') onSeek(Math.min(duration, position + 5))
        if (e.key === 'ArrowLeft') onSeek(Math.max(0, position - 5))
      }}
    />
  )
}
