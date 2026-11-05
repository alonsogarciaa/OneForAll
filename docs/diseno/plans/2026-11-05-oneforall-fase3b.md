# OneForAll — Fase 3b (Practice Mixer) Implementation Plan

**Goal:** A real-time practice mixer on a track's stems (mute/solo/volume, speed 0.50–1.00× without pitch change, loop on the waveform, global and per-stem key, metronome) that exports the mix or the loop at maximum quality.

**Architecture:** Playback runs in the renderer: one AudioContext, one Signalsmith Stretch AudioWorklet node per stem, every command scheduled at the same context time. Pure, UI-free modules in `ui/src/mixer/` (state, engine, metronome) are driven by a `MixerSheet`. The engine gets a `djengine/mixer/` package: per-track state persistence and a `mix_export` job that renders with ffmpeg `rubberband`.

**Tech Stack:** `signalsmith-stretch@1.3.2` (MIT, WASM AudioWorklet), Web Audio, React/Zustand, FastAPI + JobManager, the bundled ffmpeg (`rubberband`, `amix`, `alimiter`, `atrim`).

**Spec:** `docs/diseno/specs/2026-11-05-oneforall-fase3b-mezclador-design.md`

## Global Constraints

- Speed `rate` 0.50–1.00, step 0.01; presets 0.5 / 0.75 / 0.9 / 1.0.
- Key: global `semis` −12…+12 (int); per-stem `semis` −12…+12; effective = `clamp(global + stem, -12, 12)`.
- Stem gain 0–1.5 (double click → 1.0); master 0–1.5; gain changes use a 10 ms ramp (`setTargetAtTime`, time constant 0.01/3).
- Solo rule: if any stem has `solo`, only solo stems sound; otherwise all non-muted stems.
- If `lead_vocals` and `backing_vocals` both exist, they replace `vocals` in the mixer (vocals not loaded).
- Mixer limit: 12 min (`MIXER_MAX_SECONDS = 12 * 60`). Message: "Pista demasiado larga para el mezclador".
- All engine nodes receive the same `output` time: `ctx.currentTime + 0.05`.
- Metronome: lookahead timer 25 ms, schedule window 100 ms; count-in 0/1/2 bars; meters `2/4,3/4,4/4,6/8` → beats per bar 2/3/4/6; accent on beat 1; offset −7…+7 beats.
- State saved 500 ms after the last change (`PUT /mixer/state`).
- Export names: full → `mix.<ext>` when rate 1 and semis 0, else `mix (0.75x, +2).<ext>`; loop → `loop 01m12s-01m28s (0.75x, +2).<ext>` (the parenthesised part is omitted at 1.00× / 0). Formats = `stems_format` values `wav16|wav24|flac|mp3` (mp3 = libmp3lame 320k), 44.1 kHz stereo.
- Export filter per audible stem: `[i:a]atrim(loop only),asetpts=N/SR/TB,rubberband=tempo=R:pitch=P:pitchq=quality:transients=mixed,volume=G[si]` (rubberband omitted when R=1 and P=1), then `amix=inputs=n:normalize=0:duration=longest,volume=M,alimiter=limit=0.99:level=false`.
- CSP `script-src` becomes `'self' blob: 'wasm-unsafe-eval'`. Signalsmith creates its worklet module from a `blob:` URL; this was checked in the package source and is the only addition beyond the spec. Nothing is loaded from a CDN.
- UI copy is Spanish (Mezclador, Velocidad, Tonalidad, Metrónomo, Cuenta atrás, Compás, Exportar, Mezcla completa, Solo el bucle, Cargando stems…, Faltan stems de esta canción, Separar de nuevo, Sin BPM, No hay memoria suficiente para el mezclador).
- No new Python packages. All existing suites stay green.

## Review Focus

1. **Track never analysed (no beats, no BPM):** the mixer opens, the waveform comes from the stems, the loop does not snap, and the metronome is disabled with "Sin BPM". Tested in Task 6 (metronome) and Task 7 (sheet).
2. **A tiny drag on the waveform (under 0.25 s):** treated as a click (seek), never a zero-length loop. Tested in Task 7.
3. **Stem files of slightly different lengths (encoder padding):** export uses `duration=longest`, and the engine node loop end is clamped to the shortest buffer. Tested in Task 3 and Task 5.
4. **Closing the sheet while stems are still decoding, or reopening it quickly:** no audio keeps playing, `dispose()` runs, and the AudioContext is closed. Tested in Task 7.
5. **Paths with accents or quotes (DESPECHÁ, `Don't`):** they go to ffmpeg only as `-i` arguments, never inside the filter string. Tested in Task 4.

---

### Task 1: Signalsmith spike and runtime setup (gate)

**Files:**
- Modify: `package.json` (dependency `signalsmith-stretch@1.3.2`, exact)
- Modify: `electron.vite.config.ts` (CSP `script-src 'self' blob: 'wasm-unsafe-eval'`)
- Create: `ui/src/mixer/stretch.ts`
- Create (throwaway, not committed): a dev-only page or devtools snippet
- Create: `docs/bench/2026-11-fase3b-stretch.md`

**Interfaces:**
- Produces: `export interface StretchNode { connect(n: AudioNode): void; disconnect(): void; addBuffers(ch: Float32Array[]): Promise<number>; schedule(o: { output?: number; active?: boolean; input?: number; rate?: number; semitones?: number; loopStart?: number; loopEnd?: number }): void; stop(when?: number): void }` and `export type CreateStretch = (ctx: BaseAudioContext) => Promise<StretchNode>`, with `export const createStretch: CreateStretch` wrapping `SignalsmithStretch(ctx)` from `signalsmith-stretch/SignalsmithStretch.mjs`.

- [ ] **Step 1:** `npm i -E signalsmith-stretch@1.3.2`, change the CSP, and write `stretch.ts`.
- [ ] **Step 2: Spike.** In `npm run dev`, load 6 real stems of DESPECHÁ into 6 nodes. Schedule start at the same `output`. Run 5 min with a 4 s loop, rate 0.5 and then 0.75, and +3 semitones on one stem.
- [ ] **Step 3: Measure and record in the bench doc:**
  - drift between nodes, from `inputTime` sampled every 1 s (must stay ≤ 128 samples ≈ 2.9 ms);
  - renderer CPU in Task Manager;
  - glitches heard when moving the rate slider.
- [ ] **Step 4: Gate.** It passes if there is no drift beyond the limit, there are no dropouts, and renderer CPU stays under 40 % of one core on the Ryzen 5 5600X (if not, retry with `configure({preset: "cheaper"})`).
  - If it fails, or 0.5× sounds bad: **stop and ask the owner** about the Rubber Band WASM fallback (spec §9). Do not continue to Task 5.
- [ ] **Step 5:** `npm run build` succeeds. Then commit `package.json`, `package-lock.json`, `electron.vite.config.ts`, `ui/src/mixer/stretch.ts` and the bench doc. Message: `feat(mixer): signalsmith stretch loader and CSP; spike results`.

### Task 2: Engine mixer state (model, store, endpoints)

**Files:**
- Create: `engine/djengine/mixer/__init__.py`, `engine/djengine/mixer/state.py`
- Modify: `engine/djengine/server.py` (Services gets `mixer: MixerStore`; routes)
- Test: `engine/tests/mixer/__init__.py`, `engine/tests/mixer/test_state.py`

**Interfaces:**
- Produces:
  - `class StemState(BaseModel)`: `gain: float = 1.0 (0..1.5)`, `mute: bool = False`, `solo: bool = False`, `semis: int = 0 (-12..12)`.
  - `class Loop(BaseModel)`: `start: float >= 0`, `end: float`, with `end > start`.
  - `class Metronome(BaseModel)`: `on: bool = False`, `volume: float = 0.6 (0..1)`, `count_in: Literal[0,1,2] = 1`, `meter: Literal["2/4","3/4","4/4","6/8"] = "4/4"`, `offset: int = 0 (-7..7)`.
  - `class MixState(BaseModel)`: `version: Literal[1] = 1`, `rate: float = 1.0 (0.5..1.0)`, `semis: int = 0 (-12..12)`, `master: float = 1.0 (0..1.5)`, `stems: dict[str, StemState] = {}` (keys must be in `STEMS + KARAOKE`), `loop: Loop | None = None`, `loop_on: bool = False`, `metronome: Metronome = Metronome()`.
  - `def effective_semis(state, stem) -> int`, `def audible(state, names: list[str]) -> list[str]`.
  - `class MixerStore(db_path)` with `get(path) -> MixState | None` (invalid stored JSON → None) and `put(path, state)`. Table `mixer_state(path_key TEXT PRIMARY KEY, state_json TEXT, updated_at TEXT)`; key = `stems.store.key(path)`.
  - Routes `GET /mixer/state?path=` → `{"state": MixState | null}`, and `PUT /mixer/state {path, state}` → `{"ok": true}`. Validation errors → 422.

- [ ] **Step 1: Write failing tests:**
  - `test_defaults_and_ranges`: `MixState()` has rate 1.0; `rate=0.49` and `semis=13` raise.
  - `test_unknown_stem_rejected`: key `"kazoo"` raises.
  - `test_effective_semis_clamped`: global 10 + stem 5 gives 12.
  - `test_audible_solo_then_mute`: solo on drums means only `["drums"]`; no solo with vocals muted means everything but vocals.
  - `test_store_roundtrip_case_insensitive` (Windows only): put with `C:\X\Song.wav`, get with an uppercase path, same state.
  - `test_corrupt_row_returns_none`: write `"{bad"` directly, `get` returns None.
  - `test_api_get_put`: PUT then GET via `TestClient`; PUT with rate 2 gives 422.
- [ ] **Step 2:** `py -m uv run pytest tests/mixer/test_state.py -q` fails.
- [ ] **Step 3:** Implement. Follow `StemsStore` for the lock and `sqlite3`.
- [ ] **Step 4:** The tests pass, and so does the full engine suite.
- [ ] **Step 5:** Commit `feat(mixer): per-track mixer state model, store and API`.

### Task 3: Export filter graph (pure)

**Files:**
- Create: `engine/djengine/mixer/graph.py`
- Test: `engine/tests/mixer/test_graph.py`

**Interfaces:**
- Consumes: `MixState`, `effective_semis`, `audible` (Task 2).
- Produces:
  - `def build_mix_graph(stems: dict[str, Path], state: MixState, rng: Literal["full","loop"]) -> tuple[list[str], str]`, returning (ffmpeg input args `["-i", p, ...]` in `audible` order, and the `filter_complex` string ending in `[out]`). It raises `UserError("bad_request", "No hay ningún stem audible")` when nothing is audible, and `UserError("bad_request", "No hay bucle")` for `rng="loop"` without a loop.
  - `def output_seconds(state, duration: float, rng) -> float`.
  - `def export_name(state, rng, ext) -> str`, using the names from Global Constraints.

- [ ] **Step 1: Write failing tests:**
  - `test_identity_has_no_rubberband`: rate 1, semis 0 → `"rubberband" not in fc`, `"amix=inputs=2:normalize=0:duration=longest"` in fc.
  - `test_rate_and_pitch`: rate 0.75 and stem semis +2 → `"rubberband=tempo=0.75:pitch=1.122462"` in fc (6 decimals; 2^(2/12)).
  - `test_loop_trims_before_stretch`: loop 10–14 → `"atrim=start=10.000:end=14.000"` appears before `"rubberband"` in that stem's chain.
  - `test_muted_and_solo_excluded`: the inputs list only the audible files.
  - `test_nothing_audible_raises` and `test_loop_without_loop_raises`.
  - `test_paths_never_in_filter`: a file named `Don't – DESPECHÁ.wav` appears in the inputs and is not in fc.
  - `test_export_names`: `mix.wav`; `mix (0.75x, +2).flac`; `loop 01m12s-01m28s (0.75x).mp3` (loop 72–88, rate 0.75, semis 0).
  - `test_output_seconds`: loop 10–14 at 0.5 → 8.0.
- [ ] **Step 2:** The tests fail.
- [ ] **Step 3:** Implement. Pitch ratio is `2 ** (semis / 12)` formatted `:.6f`; rate is formatted `:.2f`. Each chain ends `volume=<gain:.3f>`. Master is `volume=<master:.3f>`, then `alimiter=limit=0.99:level=false`.
- [ ] **Step 4:** The tests pass.
- [ ] **Step 5:** Commit `feat(mixer): export filter graph builder`.

### Task 4: `mix_export` job

**Files:**
- Create: `engine/djengine/mixer/export.py`
- Modify: `engine/djengine/server.py` (`MixExportJobBody` added to the `JobBody` union; concurrency `"mix_export": 1`)
- Modify: `engine/djengine/convert.py` only if a shared progress-reading helper is extracted from `convert_file`. That is allowed only if `test_convert.py` stays green.
- Test: `engine/tests/mixer/test_export.py`

**Interfaces:**
- Consumes: `build_mix_graph`, `output_seconds`, `export_name` (Task 3); `svc.stems.get`; `_commit`; `unique_path`; `ffmpeg_error`; `svc.library.add_history`.
- Produces:
  - `class MixExportJobBody(BaseModel)`: `type: Literal["mix_export"]`, `path: str`, `state: MixState`, `range: Literal["full","loop"] = "full"`, `format: Literal["wav16","wav24","flac","mp3"] | None = None` (None → `settings.stems_format`).
  - `def make_mix_export_runner(svc, path: Path, state: MixState, rng, fmt) -> Runner`, whose result is `{"file": str}`.
  - Job stages: `rendering`, then `saving`.
  - The output file is registered so that `/stems/check` returns it (`svc.stems.add(path, "mix:<name>", final, "mix")` is not acceptable because it would pollute stem listings). Add `MixerStore.add_export(path, file)` with table `mixer_exports(file_key PRIMARY KEY, path_key)`, and make `/stems/check` also accept `svc.mixer.is_export(f)`.

- [ ] **Step 1: Write failing tests,** using stems made with soundfile: 3 s stereo sines at 440 Hz, written to a stems folder and registered via `svc.stems.add`.
  - `test_export_full_duration_and_pitch`: rate 0.5 and semis +12 → output duration ≈ 6.0 s (±0.1), and the dominant FFT frequency ≈ 880 Hz (±1 %).
  - `test_export_loop_only`: loop 1–2 at rate 1 → duration ≈ 1.0 s; the name starts with `loop 00m01s-00m02s`.
  - `test_export_name_collision_uses_unique_path`: two identical exports give `mix.wav` and `mix (1).wav`.
  - `test_export_cancel_leaves_no_file`: cancel during `rendering` → status cancelled, no new file in the folder.
  - `test_export_missing_stems`: no stems → failed with `"Faltan stems de esta canción"`.
  - `test_export_history_and_drag`: history has action `"export"` / done, and `/stems/check` confirms the output.
  - `test_export_over_12_minutes_refused`: monkeypatch `_duration` to 13 min → `UserError("too_long", "Pista demasiado larga para el mezclador")`.
- [ ] **Step 2:** The tests fail.
- [ ] **Step 3: Implement.**
  - Run ffmpeg via `asyncio.create_subprocess_exec`, with `ctx.register_process` and `-progress pipe:1`. Progress is `out_time / output_seconds`.
  - Encode args per format as in Global Constraints. Write to `ctx.tmp_dir`.
  - Call `ctx.begin_finalize()`, then `await asyncio.to_thread(_commit, tmp, final)` into the stems folder.
  - Failures are mapped with `ffmpeg_error`.
- [ ] **Step 4:** The tests pass, and so does the full engine suite.
- [ ] **Step 5:** Commit `feat(mixer): mix and loop export job (ffmpeg rubberband)`.

### Task 5: `mixState.ts` and Camelot transposition (UI, pure)

**Files:**
- Create: `ui/src/mixer/mixState.ts`, `ui/src/mixer/mixState.test.ts`
- Modify: `ui/src/lib/camelot.ts` and `ui/src/lib/camelot.test.ts`

**Interfaces:**
- Produces:
  - TS types mirroring Task 2 (`MixState`, `StemState`, `Loop`, `Metronome`, with the same field names).
  - `defaultState(): MixState`; `parseState(x: unknown): MixState`, which falls back to defaults on any invalid field and clamps numbers.
  - `effectiveSemis(s, stem): number`; `audible(s, names): string[]`.
  - `mixerStems(list: {stem: string; file: string}[]): {stem: string; file: string}[]`, which applies the karaoke replacement rule and `names` order `vocals, lead_vocals, backing_vocals, drums, bass, guitar, piano, other`.
  - `camelotShift(code: string, semis: number): string`, where +1 semitone = +7 on the wheel, mod 12, keeping the letter.

- [ ] **Step 1: Write failing tests:**
  - `parseState({rate: 3})` → rate 1.0 (invalid field dropped to its default);
  - `parseState(null)` equals `defaultState()`;
  - the solo/mute cases from Task 2;
  - `mixerStems` with vocals + lead + backing → no `vocals`;
  - `camelotShift('8A', 2) === '10A'`, `camelotShift('8A', -1) === '1A'`, `camelotShift('12B', 12) === '12B'`.
- [ ] **Step 2:** `npx vitest run ui/src/mixer ui/src/lib/camelot.test.ts` fails.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** The tests pass.
- [ ] **Step 5:** Commit `feat(mixer): mix state and camelot transposition helpers`.

### Task 6: `MixerEngine` and metronome (UI audio, pure modules)

**Files:**
- Create: `ui/src/mixer/engine.ts`, `ui/src/mixer/engine.test.ts`, `ui/src/mixer/metronome.ts`, `ui/src/mixer/metronome.test.ts`, `ui/src/mixer/fakeAudio.ts` (test fake: AudioContext with settable `currentTime`, gain nodes recording `setTargetAtTime`, oscillators recording `start` times, and a `CreateStretch` returning recorder nodes)

**Interfaces:**
- Consumes: `CreateStretch`, `StretchNode` (Task 1); `MixState`, `effectiveSemis`, `audible` (Task 5).
- Produces:
  - `class MixerEngine`, built with `new MixerEngine(ctx: BaseAudioContext, createStretch: CreateStretch)`:
    - `load(stems: {stem: string; channels: Float32Array[]}[], onProgress?: (n: number) => void): Promise<void>`;
    - `apply(state: MixState): void`, which sets rate, semis, gains and loop; when playing, the reschedule happens at `now + 0.05` on every node;
    - `play(): void`, `pause(): void`, `seek(t: number): void`, `position(): number` (song seconds, wrapped inside the loop when `loop_on`), `duration: number` (the shortest buffer), `playing: boolean`, `onTick?: (songTime: number) => void`, `dispose(): Promise<void>` (stops and disconnects every node, then `ctx.close()`).
  - `metronome.ts`:
    - `beatsPerBar(meter): number`;
    - `clickTimes(beats: number[] | null, bpm: number | null, from: number, to: number, meter, offset): {t: number; accent: boolean}[]`, in song seconds. With no beats, it uses a grid every 60/bpm from 0; with neither, `[]`.
    - `class Metronome`, built with `new Metronome(ctx, songToCtx: (songT: number) => number | null)`, with `start(state, beats, bpm)`, `stop()`, and `countIn(bars, bpm, rate, meter): number`, which schedules the count-in clicks and returns the ctx time at which audio must start.

- [ ] **Step 1: Write failing tests (`engine.test.ts`, with the fakes):**
  - `play schedules every node at the same output and input`: every recorder got `{active: true, output: t0 + 0.05, input: 0}` with identical `output`;
  - `solo mutes the others with a 10 ms ramp`: the drums solo gain target is 1, the others 0, with time constant 0.01/3;
  - `rate change while playing reschedules all nodes at now+0.05` and `position()` follows the rate (advance fake time 2 s at rate 0.5 → about 1 s);
  - `loop_on sets loopStart/loopEnd, clamped to the shortest buffer, and position wraps`;
  - `seek while playing reschedules the input on all nodes`;
  - `dispose stops nodes and closes the context`.
- [ ] **Step 2: Write failing tests (`metronome.test.ts`):**
  - `clickTimes` on beats `[0.5, 1.0, 1.5, 2.0, 2.5]` with 4/4 and offset 0 → accents at 0.5 and 2.5;
  - offset 1 moves the accent to 1.0;
  - no beats with bpm 120 → grid 0, 0.5, …;
  - neither → `[]`;
  - `countIn(1, 120, 0.5, '4/4')` schedules 4 clicks 1.0 s apart and returns the time of the fifth;
  - the scheduler only schedules clicks inside a 100 ms window per 25 ms tick.
- [ ] **Step 3:** The tests fail.
- [ ] **Step 4:** Implement.
  - Engine time mapping: keep `(ctxT0, songT0, rate)` and recompute it on every reschedule. `songToCtx(s) = ctxT0 + (s - songT0) / rate`, with loop wrapping when `loop_on`.
  - Clicks are a short sine (1000 Hz, or 1500 Hz on the accent), 30 ms long, with an exponential decay gain.
- [ ] **Step 5:** The tests pass.
- [ ] **Step 6:** Commit `feat(mixer): audio engine and metronome`.

### Task 7: `MixerSheet` (load, waveform loop, transport, strips, globals, save)

**Files:**
- Create: `ui/src/components/MixerSheet.tsx`, `ui/src/components/MixerSheet.test.tsx`, `ui/src/components/mixer.css`
- Modify: `ui/src/components/Waveform.tsx` (optional props `loop?: {start: number; end: number} | null`, `onLoop?(start: number, end: number): void`, `snap?: number[]`; a drag under 0.25 s counts as a seek; `Alt` disables snap)
- Modify: `ui/src/lib/engineClient.ts` (`getMixerState(path)`, `putMixerState(path, state)`, `mixExport(path, state, range, format?)`)
- Modify: `ui/src/stores/uiStore.ts` (`mixerFor: string | null`, `openMixer(path)`, `closeMixer()`), `ui/src/App.tsx` (`MixerSheetHost`)
- Modify: `ui/src/components/StemsSection.tsx`, `ui/src/components/StemsSheet.tsx` (a "Mezclador" button when there are ≥ 2 stems)

**Interfaces:**
- Consumes: Tasks 1, 5 and 6; `client.getStems`, `client.getAnalysis` (a 404 means no analysis), `client.audioUrl`.
- Produces: `MixerSheet({path, onClose})`, plus the `uiStore.openMixer` entry used by the buttons.

- [ ] **Step 1: Write failing tests** (with `MixerEngine` mocked via `vi.mock('../mixer/engine')`, and `fetch` / `decodeAudioData` stubbed):
  - shows "Cargando stems… 1/3" and then the strips in `mixerStems` order;
  - an S click calls `apply` with that stem solo;
  - the speed preset 0.75 shows "BPM 128,0 → 96,0";
  - key +2 shows "8A → 10A" (with Camelot notation);
  - `putMixerState` is called once, 500 ms after three quick changes (fake timers);
  - a saved state from `getMixerState` is applied on open;
  - with no analysis, the metronome toggle is disabled and "Sin BPM" is shown;
  - a missing stem (fetch 404) shows "Faltan stems de esta canción" and the "Separar de nuevo" button;
  - unmounting during load calls `dispose` and never calls `play`;
  - `Space` toggles play but not while typing in an input;
  - `L` toggles the loop.
  - In `Waveform`: a drag from 10 s to 10.1 s calls `onSeek` and not `onLoop`; a drag from 10 s to 14 s with snap beats calls `onLoop` with the nearest beats.
- [ ] **Step 2:** `npx vitest run ui/src/components/MixerSheet.test.tsx` fails.
- [ ] **Step 3: Implement.**
  - Layout follows spec §3 and `Liquid_Glass.md`. Reuse `GlassSheet` (wide), `btn`/`btn-sm`, and the stem colours from `stems.css`.
  - Duration over 12 min → message, and nothing is loaded.
  - No analysis: build the waveform peaks in the app from the summed stem channels (2000 buckets, the same shape as `AnalysisSidecar['waveform']`, with every band set from the peaks), and pass no `snap`.
  - `decodeAudioData` failing with a `RangeError` or out-of-memory error → "No hay memoria suficiente para el mezclador".
  - Release each `AudioBuffer` after `load`.
  - If the context is `suspended`, call `ctx.resume()` on play.
- [ ] **Step 4:** The tests pass, and so does the whole Vitest suite.
- [ ] **Step 5:** Verify in the browser: `npm run dev`, then check the mixer at desktop width and at 375 px (strips stack, no horizontal scroll), in light and dark.
- [ ] **Step 6:** Commit `feat(ui): practice mixer sheet`.

### Task 8: Metronome panel and export menu in the sheet

**Files:**
- Modify: `ui/src/components/MixerSheet.tsx`, `MixerSheet.test.tsx`, `mixer.css`

**Interfaces:**
- Consumes: `Metronome` (Task 6); `client.mixExport` (Task 7); the jobs store for progress; `window.oneforall.allowDrag` / `startDrag` for the result.

- [ ] **Step 1: Write failing tests:**
  - turning the metronome on with count-in 1 and play → `countIn` is called, and the engine `play` happens at the returned time;
  - changing the meter / offset → `apply` saves them;
  - "Solo el bucle" is disabled without a loop;
  - "Mezcla completa" WAV calls `mixExport(path, state, 'full', 'wav16')` and shows the job progress;
  - a done job shows the file with "Mostrar en carpeta" and is draggable (`allowDrag` called with the file).
- [ ] **Step 2:** The tests fail.
- [ ] **Step 3:** Implement. The metronome is not part of the export (spec). The menu also has "Stems (zip)", which calls the existing `client.zipStems`.
- [ ] **Step 4:** The tests pass. Repeat the 375 px and dark-mode check.
- [ ] **Step 5:** Commit `feat(ui): mixer metronome and export`.

### Task 9: E2E, build, manual listening, summary

**Files:**
- Modify: `e2e/app.spec.ts` (new test)
- Create: `docs/diseno/fase3b-resumen.md`
- Modify: `README.md` (licence table: `signalsmith-stretch` MIT)

- [ ] **Step 1: Write an E2E test** with the fake engine. Separate stems from the library, open "Mezclador", set speed 0.75, drag a loop on the waveform, export "Solo el bucle" (WAV), and wait for the job to be done. Then close the mixer, reopen it, and check that the speed still shows 0.75.
- [ ] **Step 2:** `npm run build && npx playwright test` → all pass (previous 7 + 1).
- [ ] **Step 3:** Run the full suites: `cd engine && py -m uv run pytest -q`, then `npx vitest run`.
- [ ] **Step 4:** `npm run dist`, install, and run the manual listening check from spec §7 on DESPECHÁ: live and exported at 0.5× and +3, 5 min in a loop with no drift, no clicks when moving the sliders. Record the results in the summary.
- [ ] **Step 5:** Commit `test(e2e): mixer flow; docs: phase 3b summary`.
