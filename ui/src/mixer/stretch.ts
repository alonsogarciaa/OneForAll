// Real-time tempo/pitch per stem: Signalsmith Stretch (MIT), a WASM AudioWorklet node.
import SignalsmithStretch from 'signalsmith-stretch/SignalsmithStretch.mjs'

export interface StretchSchedule {
  output?: number
  active?: boolean
  input?: number
  rate?: number
  semitones?: number
  loopStart?: number
  loopEnd?: number
}

export interface StretchNode {
  connect(n: AudioNode): void
  disconnect(): void
  addBuffers(ch: Float32Array[]): Promise<number>
  schedule(o: StretchSchedule): void
  stop(when?: number): void
}

export type CreateStretch = (ctx: BaseAudioContext) => Promise<StretchNode>

export const createStretch: CreateStretch = (ctx) => SignalsmithStretch(ctx) as unknown as Promise<StretchNode>
