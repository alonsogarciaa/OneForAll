// Test fakes for Web Audio and the stretch node (used only by tests).
import type { StretchNode, StretchSchedule } from './stretch'

export class FakeParam {
  calls: { fn: string; v: number; t: number; tc?: number }[] = []
  constructor(public value = 1) {}
  setTargetAtTime(v: number, t: number, tc: number) {
    this.calls.push({ fn: 'target', v, t, tc })
    this.value = v
  }
  setValueAtTime(v: number, t: number) {
    this.calls.push({ fn: 'set', v, t })
    this.value = v
  }
  exponentialRampToValueAtTime(v: number, t: number) {
    this.calls.push({ fn: 'exp', v, t })
  }
}

export class FakeGain {
  gain = new FakeParam(1)
  connect() {}
  disconnect() {}
}

export class FakeOsc {
  frequency = new FakeParam(440)
  startedAt: number | null = null
  stoppedAt: number | null = null
  connect() {}
  start(t: number) {
    this.startedAt = t
  }
  stop(t = 0) {
    this.stoppedAt = t
  }
}

export class FakeCtx {
  currentTime = 0
  sampleRate = 44100
  state = 'running'
  closed = false
  destination = {}
  gains: FakeGain[] = []
  oscs: FakeOsc[] = []
  createGain() {
    const g = new FakeGain()
    this.gains.push(g)
    return g
  }
  createOscillator() {
    const o = new FakeOsc()
    this.oscs.push(o)
    return o
  }
  async close() {
    this.closed = true
  }
  async resume() {
    this.state = 'running'
  }
}

export class RecorderNode implements StretchNode {
  schedules: StretchSchedule[] = []
  buffers: Float32Array[][] = []
  stopped = false
  disconnected = false
  connect() {}
  disconnect() {
    this.disconnected = true
  }
  async addBuffers(ch: Float32Array[]) {
    this.buffers.push(ch)
    return ch[0].length / 44100
  }
  schedule(o: StretchSchedule) {
    this.schedules.push(o)
  }
  stop() {
    this.stopped = true
  }
}

export function recorderFactory(nodes: RecorderNode[]) {
  return async () => {
    const n = new RecorderNode()
    nodes.push(n)
    return n
  }
}

export const seconds = (s: number) => [new Float32Array(Math.round(s * 44100)), new Float32Array(Math.round(s * 44100))]
