declare module 'signalsmith-stretch/SignalsmithStretch.mjs' {
  const SignalsmithStretch: (ctx: BaseAudioContext, options?: AudioWorkletNodeOptions) => Promise<AudioWorkletNode>
  export default SignalsmithStretch
}
