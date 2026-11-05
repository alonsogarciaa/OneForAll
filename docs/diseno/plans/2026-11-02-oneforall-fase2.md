# OneForAll — Fase 2 (Análisis DJ) Implementation Plan

**Goal:** Add BPM, key (Camelot), loudness, waveform and beat grid analysis to OneForAll, with a data sheet (waveform + player + tap tempo), a harmonic-mixing screen, auto-analysis after downloads, and a GiantSteps benchmark that picks the methods.

**Architecture:** A new `djengine/analysis/` package holds pure, separately testable estimators behind one interface each (tempo, key, loudness, waveform, camelot). An `analysis` job type runs them through the existing JobManager, caches results in a new `analyses` table plus a JSON sidecar, and writes tags. The benchmark (`engine/bench/`) runs every candidate on GiantSteps and fixes the defaults in `analysis/config.py`. The UI adds columns, a data sheet and an "Armonía" screen.

**Tech Stack:** existing stack plus librosa, numpy, scipy, pyloudnorm, soundfile; candidates deeprhythm (PyTorch CPU) and madmom's key CNN (built from source or ported to numpy).

**Spec:** `docs/diseno/specs/2026-11-02-oneforall-fase2-analisis-design.md` (base: `docs/diseno/specs/2026-11-01-dj-app-design.md`)

## Global Constraints

- Python 3.12, uv, engine tests: `cd engine && py -m uv run pytest -q`. UI: `npx vitest run`. E2E: `npm run build && npx playwright test`.
- Decode audio only through ffmpeg (`find_tool("ffmpeg")`), mono float32; sample rate 22050 for tempo/key/waveform, 44100 stereo for loudness.
- DJ BPM range default 70–180 (settings `bpm_min`, `bpm_max`); BPM shown with 1 decimal; `TBPM` tag written as rounded integer.
- Key display always «CAMELOT · musical-es», e.g. «8A · Lam». Tag notation from setting `key_notation`: `camelot` (default) or `musical` (`Am`, `F#`).
- `ANALYSIS_VERSION = 1`.
- Acceptance thresholds (spec §6): tempo **Accuracy2 ≥ 90 %**, key **MIREX ≥ 0.80** (if key falls short, stop and ask the owner).
- Camelot wheel (exact mapping used everywhere):
  `1A G#m/Abm · 2A D#m/Ebm · 3A A#m/Bbm · 4A Fm · 5A Cm · 6A Gm · 7A Dm · 8A Am · 9A Em · 10A Bm · 11A F#m · 12A C#m/Dbm`;
  `1B B · 2B F# · 3B C# · 4B G# · 5B D# · 6B A# · 7B F · 8B C · 9B G · 10B D · 11B A · 12B E`.
- Spanish note names for display: Do, Do#, Re, Re#, Mi, Fa, Fa#, Sol, Sol#, La, La#, Si; minor suffix `m` (e.g. `Lam`, `Fa#m`), major without suffix.
- All UI copy Spanish; UI tasks use the `impeccable` skill rules already in DESIGN of Phase 1 (Liquid Glass tokens, no text < 14px on glass).
- madmom key weights are CC BY-NC-SA: record it in README and Ajustes → "Acerca de".

## Review Focus

1. Very short or silent audio (≤ 10 s, digital silence) → analysis completes with low confidence, no crash, no NaN in DB/JSON. Tested in Task 2/3/4.
2. File edited after analysis (same path, new mtime/size) → cache miss and re-analysis; unchanged file → cache hit. Tested in Task 9.
3. Manual BPM then "Reanalizar" → manual BPM kept unless `reset_bpm`. Tested in Task 9.
4. Auto-analysis for playlist children and a failed/cancelled analysis never marks the download failed. Tested in Task 10.
5. `/audio` path abuse (`..`, non-audio extension, file outside library/analyses/session picks) → 403. Tested in Task 10.

---

### Task 1: Dependencies, audio decoding and Camelot

**Files:** Modify `engine/pyproject.toml`. Create `engine/djengine/analysis/__init__.py`, `audio_io.py`, `camelot.py`. Test `engine/tests/analysis/test_camelot.py`, `test_audio_io.py`, `engine/tests/analysis/conftest.py`.

**Interfaces — Produces:**
- `decode(path: Path, sr: int = 22050, mono: bool = True) -> np.ndarray` (float32; shape `(n,)` mono or `(2, n)` stereo). Raises `UserError("unreadable", "No se puede leer el audio de este archivo")`.
- `PITCHES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]`; `to_camelot(tonic: str, mode: Literal["major","minor"]) -> str`; `from_camelot(code) -> tuple[str, str]`; `display_key(tonic, mode) -> str` («8A · Lam»); `tag_key(tonic, mode, notation) -> str` (`8A` or `Am`/`F#`); `compatible(a: str, b: str) -> Literal["same","adjacent","relative"] | None`.
- conftest fixtures: `click_track(bpm, seconds=30, sr=22050) -> np.ndarray`, `chord_progression(tonic, mode, seconds=30, sr=22050) -> np.ndarray` (i–iv–v–i triads with harmonics, minor uses natural minor), `write_wav(y, sr, path)`.

- [ ] **Step 1:** add deps `librosa numpy scipy pyloudnorm soundfile`; `uv sync`. Run `py -m uv run python -c "import librosa, pyloudnorm, soundfile"` → exit 0.
- [ ] **Step 2: failing tests**: all 24 rows of the wheel above (`to_camelot("A","minor")=="8A"`, `to_camelot("C","major")=="8B"`, round-trip `from_camelot`), `display_key("F#","minor")=="11A · Fa#m"`, `tag_key("A","minor","musical")=="Am"`, `compatible("8A","8A")=="same"`, `("8A","9A")=="adjacent"`, `("12A","1A")=="adjacent"`, `("8A","8B")=="relative"`, `("8A","10A") is None`; decode of a written 3 s stereo sine returns length ≈ 3·sr, mono, max ≈ amplitude; decode of a text file raises `UserError` code `unreadable`.
- [ ] **Step 3:** run `py -m uv run pytest tests/analysis -q` → FAIL.
- [ ] **Step 4:** implement (`decode`: `ffmpeg -v error -nostdin -i path -f f32le -ac 1|2 -ar sr pipe:1`, `np.frombuffer`).
- [ ] **Step 5:** run → PASS. Commit `feat(analysis): audio decoding and camelot wheel`.

---

### Task 2: Tempo — librosa method and DJ-range folding

**Files:** Create `engine/djengine/analysis/tempo.py`. Test `engine/tests/analysis/test_tempo.py`.

**Interfaces — Consumes:** Task 1 fixtures. **Produces:** `TempoResult(bpm: float, confidence: float, beats: list[float])` dataclass; `fold_bpm(bpm, lo=70, hi=180) -> float`; `estimate_tempo(y, sr, method="librosa", lo=70, hi=180) -> TempoResult`; registry `TEMPO_METHODS: dict[str, Callable]`.

- librosa method: onset envelope (`librosa.onset.onset_strength`, `aggregate=np.median`), `librosa.feature.tempo` with `prior` none, refine by autocorrelation peak to 0.1 BPM, `librosa.beat.beat_track(bpm=...)` for beats; confidence = normalized autocorrelation peak height (0–1).

- [ ] **Step 1: failing tests**: clicks 128 → 128 ± 0.5; 64 → folded 128 ± 0.5; 174 → 174 ± 0.5; 90 → 90 ± 0.5; `fold_bpm(64)==128`, `fold_bpm(200)==100`, `fold_bpm(181, hi=180)==90.5`; beats spacing ≈ 60/128 s; 5 s of silence → bpm finite, confidence < 0.3, no exception.
- [ ] **Step 2:** run → FAIL. **Step 3:** implement. **Step 4:** run → PASS. Commit `feat(analysis): librosa tempo with dj-range folding`.

---

### Task 3: Key — profile methods

**Files:** Create `engine/djengine/analysis/key.py`, `engine/djengine/analysis/profiles.py`. Test `engine/tests/analysis/test_key.py`.

**Interfaces — Produces:** `KeyResult(tonic: str, mode: str, camelot: str, confidence: float)`; `estimate_key(y, sr, method="edma") -> KeyResult`; `KEY_METHODS` registry (`edma`, `temperley`, `krumhansl`; `cnn` added in Task 7). `profiles.py` holds the 12-value major/minor vectors for each profile (Krumhansl-Kessler, Temperley 2007, Faraldo EDMA).

- Algorithm: `librosa.feature.chroma_cqt` (hop 4096, bins_per_octave 36), mean over time, L2-normalize; Pearson correlation with each of 24 rotated profiles; best = key; confidence = (best − second) / best clipped 0–1.

- [ ] **Step 1: failing tests** (parametrize over the three profiles): A minor progression → `("A","minor","8A")`; C major → `8B`; F# minor → `11A`; silence → result returned with confidence 0.
- [ ] **Step 2–4:** fail → implement → pass. Commit `feat(analysis): template key estimation (edma, temperley, krumhansl)`.

---

### Task 4: Loudness and waveform

**Files:** Create `engine/djengine/analysis/loudness.py`, `waveform.py`. Test `engine/tests/analysis/test_loudness_waveform.py`.

**Interfaces — Produces:** `measure(y_stereo: np.ndarray, sr: int) -> tuple[float | None, float]` (LUFS integrated, `None` if too short/silent; peak dBFS, `-inf` → `-120.0`); `compute(y, sr, buckets=2000) -> dict[str, list[float]]` keys `peaks, low, mid, high`, each `buckets` long, values rounded to 3 decimals in 0–1.

- [ ] **Step 1: failing tests**: stereo 1 kHz sine at −20 dBFS peak → peak −20.0 ± 0.1, LUFS ≈ −23.0 ± 0.7 (pyloudnorm reference for full-scale sine minus 3 dB); silence → LUFS `None`, peak −120.0; waveform of 80 Hz tone → mean(low) > 3·mean(high); silence → all zeros; length == buckets for a 1 s file and a 10 min file.
- [ ] **Step 2–4:** fail → implement (bands via `scipy.signal.butter` sos filters <250 Hz, 250–4000, >4000; per-bucket RMS, normalize by global max) → pass. Commit `feat(analysis): loudness and 3-band waveform`.

---

### Task 5: Benchmark harness (GiantSteps)

**Files:** Create `engine/bench/__init__.py`, `engine/bench/metrics.py`, `engine/bench/fetch_giantsteps.py`, `engine/bench/run.py`. Test `engine/tests/test_bench_metrics.py`. Modify `.gitignore` (`engine/bench/data/`), `engine/pyproject.toml` (marker `bench`).

**Interfaces — Produces:**
- `metrics.accuracy1(pred: float, ref: float) -> bool` (|p−r| ≤ 4 % of r); `accuracy2(pred, ref) -> bool` (accuracy1 against r × {1, 2, ½, 3, ⅓}); `mirex_score(pred: str, ref: str) -> float` (Camelot codes; exact 1.0, perfect fifth either direction 0.5 = same letter ±1, relative 0.3 = same number other letter, parallel 0.2 = same tonic other mode, else 0).
- `fetch_giantsteps.py`: clones/downloads annotations of *GiantSteps Key* (github.com/GiantSteps/giantsteps-key-dataset) and *GiantSteps Tempo* (github.com/GiantSteps/giantsteps-tempo-dataset; use the revised annotations from github.com/hendriks73/giantsteps-tempo-dataset when present), then fetches the audio previews listed by each dataset's own download script into `engine/bench/data/{key,tempo}/`; prints `downloaded N/M`. Audio stays local and is git-ignored.
- `run.py --tempo librosa,deeprhythm --key edma,temperley,krumhansl,cnn` → writes `docs/bench/2026-11-fase2.md` with a table per task (method, N, Accuracy1, Accuracy2 / MIREX, exact, sec/track) and `engine/bench/results.json`.

- [ ] **Step 1: failing tests** for metrics: `accuracy1(126,128)` true, `accuracy1(122,128)` false, `accuracy2(64,128)` true, `accuracy2(43,128)` true (⅓), `mirex_score("8A","8A")==1`, `("9A","8A")==0.5`, `("8B","8A")==0.3` (relative), `("11B","8A")==0.2` (parallel: A major vs A minor), `("5B","8A")==0`.
- [ ] **Step 2–4:** fail → implement metrics → pass.
- [ ] **Step 5:** run `py -m uv run python -m bench.fetch_giantsteps` → prints downloaded counts (record them in the ledger; if fewer than 300 key / 300 tempo tracks, note it).
- [ ] **Step 6:** run `py -m uv run python -m bench.run --tempo librosa --key edma,temperley,krumhansl` → report file exists (baseline numbers recorded in ledger). Commit `feat(bench): giantsteps harness and metrics`.

---

### Task 6: Tempo candidate — deeprhythm

**Files:** Create `engine/djengine/analysis/tempo_deeprhythm.py`. Modify `engine/pyproject.toml` (optional group `nn`: `deeprhythm`, `torch` CPU wheel index `https://download.pytorch.org/whl/cpu`). Test `engine/tests/analysis/test_tempo_deeprhythm.py`.

**Interfaces — Produces:** registers `TEMPO_METHODS["deeprhythm"]`: predicts BPM on the decoded file (model loaded once, lazily, thread-safe), then folds and takes beats from librosa `beat_track(bpm=...)`; confidence from the model's softmax max. If torch import fails → raises `AnalysisUnavailable`, and `estimate_tempo` falls back to librosa with a logged warning.

- [ ] **Step 1: failing tests**: clicks 128 → 128 ± 1; fallback test: monkeypatch import to fail → `estimate_tempo(method="deeprhythm")` returns a librosa result and logs `deeprhythm unavailable`.
- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5:** run bench with `--tempo librosa,deeprhythm` → record Accuracy1/2 in ledger. Commit `feat(analysis): deeprhythm tempo candidate`.

---

### Task 7: Key candidate — madmom CNN

**Files:** Create `engine/djengine/analysis/key_cnn.py`, `engine/tests/analysis/test_key_cnn.py`, `engine/tests/fixtures/cnn_key_reference.json`. Modify `engine/pyproject.toml` / README (license note).

**Interfaces — Produces:** registers `KEY_METHODS["cnn"]`: `CnnKey.predict(y, sr) -> KeyResult` with probabilities over 24 keys; confidence = top probability.

- [ ] **Step 1 (route A):** try `py -m uv pip install "madmom @ git+https://github.com/CPJKU/madmom"` in the engine env (needs MSVC Build Tools; if missing, do NOT install system tools without asking the owner — go to route B). If it imports, wrap `madmom.features.key.CNNKeyRecognitionProcessor` + `key_prediction_to_label`.
- [ ] **Step 1 (route B, if A fails):** port inference to numpy: replicate madmom's preprocessing (`LogarithmicFilteredSpectrogramProcessor`, frame size 8192, fps 5, 24 bands/octave, 65–2100 Hz, log mag) and the CNN forward pass, loading the original weights file from madmom's `models` repository (CC BY-NC-SA). Produce `cnn_key_reference.json` by running real madmom once under WSL or Docker (ask the owner if neither is available) on 5 GiantSteps clips: expected 24-way probabilities.
- [ ] **Step 2: failing tests**: A minor progression → `8A`; route B only: for each reference clip, probabilities match within 1e-3 and argmax equal.
- [ ] **Step 3–4:** implement → pass.
- [ ] **Step 5:** bench `--key edma,temperley,krumhansl,cnn` → record MIREX in ledger. Commit `feat(analysis): madmom cnn key candidate`.

---

### Task 8: Pick the winners (gate)

**Files:** Create `engine/djengine/analysis/config.py`, `docs/bench/2026-11-fase2.md` (generated, committed). Test `engine/tests/analysis/test_config.py`.

**Interfaces — Produces:** `DEFAULT_TEMPO_METHOD: str`, `DEFAULT_KEY_METHOD: str`, `ANALYSIS_VERSION = 1`, chosen by the rule in spec §6 (best Accuracy2, tie → Accuracy1, tie < 1 pt → faster; key: best MIREX, tie → faster).

- [ ] **Step 1:** run full bench `py -m uv run python -m bench.run --tempo librosa,deeprhythm --key edma,temperley,krumhansl,cnn`.
- [ ] **Step 2:** write `config.py` from `results.json`; test asserts the constants match the winners in `results.json`.
- [ ] **Step 3: gate.** If tempo Accuracy2 < 90 % or key MIREX < 0.80: STOP, report the table to the owner and wait for a decision before Task 9. Otherwise continue.
- [ ] **Step 4:** commit `chore(analysis): pick default methods from giantsteps benchmark`.

---

### Task 9: Storage, runner, tags and settings

**Files:** Create `engine/djengine/analysis/store.py`, `engine/djengine/analysis/runner.py`. Modify `engine/djengine/library.py` (migration: `tracks.lufs`, `tracks.analyzed_at`; `set_track_analysis(...)`), `engine/djengine/settings.py`, `engine/djengine/tags.py` (key notation already supported via `TrackMeta.key`). Test `engine/tests/analysis/test_store_runner.py`.

**Interfaces — Produces:**
- `Settings` adds `analyze_on_download: bool = True`, `key_notation: Literal["camelot","musical"] = "camelot"`, `bpm_min: int = 70`, `bpm_max: int = 180` (validator `bpm_min < bpm_max`, range 40–250).
- `AnalysisRecord` dataclass (all `analyses` columns from spec §3.2) and `AnalysisStore(db_path, sidecar_dir)`: `get(path) -> AnalysisRecord | None` (valid only if size+mtime match), `get_sidecar(path) -> dict | None`, `save(rec, sidecar: dict)` (JSON written atomically: tmp + `os.replace`), `set_manual_bpm(path, bpm)`, `delete(path)`.
- `make_analysis_runner(svc, path: Path, force=False, reset_bpm=False) -> Runner`: cache hit and not force → returns cached; stages `decoding, tempo, key, loudness, waveform, saving` with `ctx.check_cancelled()` between; `ctx.begin_finalize()` before saving; on save: store row + sidecar, `library.set_track_analysis` when the path is a library track, write tags `TrackMeta(bpm=round, key=tag_key(...))` keeping existing title/artist via `read_tags` (tag errors logged, not fatal). Manual BPM preserved unless `reset_bpm`. Returns `{"path", "bpm", "camelot", "display_key", "lufs"}`.
- CPU-heavy steps run in `asyncio.to_thread`.

- [ ] **Step 1: failing tests**: runner on a 30 s 128-BPM A-minor wav (clicks + chords mixed) → DB row bpm 128 ± 1, camelot `8A`, sidecar has `beats` and 2000-bucket `waveform`, file tag `TBPM=128`, `TKEY=8A`; with `key_notation="musical"` → `TKEY=Am`; second run → cache hit (decode not called, monkeypatched counter); touch file (mtime change) → re-analysed; manual BPM 127.0 then re-run → 127.0 kept, `bpm_source="manual"`; `reset_bpm=True` → auto value; cancel during `key` stage → no row, no sidecar; 3 s silent file → completes, no NaN (`json.dumps(..., allow_nan=False)` succeeds).
- [ ] **Step 2–4:** fail → implement → pass (`py -m uv run pytest -q`). Commit `feat(analysis): cached analysis runner with tags and settings`.

---

### Task 10: API, auto-analysis and audio serving

**Files:** Modify `engine/djengine/server.py`, `engine/djengine/pipelines.py`, `engine/djengine/fakes.py`. Test `engine/tests/test_api_analysis.py`, additions to `engine/tests/test_pipelines.py`.

**Interfaces — Produces:**
- JobManager concurrency adds `"analysis": 2`.
- `POST /jobs {"type":"analysis","paths":[...],"force":false,"reset_bpm":false}` → `{"jobs":[...]}`; payload kept for retry. Session-picked paths are remembered in `svc.allowed_paths: set[str]`.
- `GET /analysis?path=` → `{"record": AnalysisRecord, "sidecar": {...}}` or 404 `{code:"not_analyzed"}`.
- `PUT /analysis/bpm {"path","bpm"}` → updated record (also library + tag).
- `GET /harmonic?ref_track=<id>|bpm=&camelot=&bpm_tolerance=6` → `[{track: TrackRecord, level, bpm_diff_pct}]` sorted level (same, adjacent, relative) then |bpm_diff|; candidates match within tolerance at ×1, ×2 or ×½ BPM; the reference track itself excluded.
- `GET /audio?path=&token=` → `FileResponse` (Range supported by Starlette); 403 unless suffix in audio set AND path (resolved) is a library track path, an `analyses` path, or in `allowed_paths`.
- Library list includes `bpm, camelot, musical_key, lufs, analyzed_at` (already columns) and `GET /library` gains `analysis_version_outdated: bool` per track.
- Auto-analysis: in `make_download_runner`, after the track is committed and recorded, if `settings.analyze_on_download` → `svc.jobs.submit("analysis", title, make_analysis_runner(svc, final))` as a top-level job (never a child, so the playlist summary is not delayed). Failure/cancel of analysis never changes the download job.
- Fake mode: the fake tone stays 5 s; analysis runs for real on it.

- [ ] **Step 1: failing tests**: download (fake) with `analyze_on_download` → an `analysis` job appears and ends `done`; playlist of 3 (fake) → 2 analysis jobs (the private one failed download) all `done`; with setting off → none; analysis cancelled → the download job stays `done`; `/audio` 403 for `C:/Windows/win.ini`, for `../` traversal of a library path, for a `.exe` placed next to a track; 200 with `Range: bytes=0-99` → 206 and 100 bytes; `/harmonic` with library fixtures (8A@128, 8A@64, 9A@130, 8B@127, 3A@128, 8A@150) and ref 8A@128 tol 6 → order `[8A@128-equivalent rows..., 9A, 8B]`, 3A and 8A@150 excluded; `PUT /analysis/bpm` writes tag.
- [ ] **Step 2–4:** fail → implement → pass (`py -m uv run pytest -q`). Commit `feat(engine): analysis api, harmonic search, audio serving, auto-analysis`.

---

### Task 11: UI — types, client, key chip, library and history columns

**Files:** Modify `ui/src/lib/types.ts`, `ui/src/lib/engineClient.ts`, `ui/src/screens/LibraryScreen.tsx`, `ui/src/screens/HistoryScreen.tsx`, `ui/src/screens/tables.css`. Create `ui/src/components/KeyChip.tsx`, `ui/src/lib/camelot.ts`. Tests `ui/src/lib/camelot.test.ts`, `ui/src/screens/LibraryScreen.test.tsx` (extend).

**Interfaces — Produces:**
- `camelot.ts`: `displayKey(camelot: string): string` («8A · Lam», same table as Global Constraints), `camelotHue(code): number` (1→0°, step 30°), `compatLabel(level) -> 'Misma clave' | '±1' | 'Relativa'`.
- Client: `analyze(paths: string[], opts?: {force?: boolean; reset_bpm?: boolean})`, `getAnalysis(path)`, `setManualBpm(path, bpm)`, `harmonic(params)`, `audioUrl(path): string` (includes token).
- `KeyChip({camelot})`: pill with `hsl(hue 70% 45%)` background and white text (contrast checked ≥ 4.5:1 in dark and light; if a hue fails, darken that hue's lightness).
- Library: columns BPM (1 decimal, «—» if none), Tonalidad (KeyChip), LUFS; toolbar «Analizar seleccionadas (N)» and «Analizar archivo…» (file input; picked path sent to `analyze`, then opens the data sheet); row double-click opens the data sheet (Task 12) instead of opening the file; context button «Abrir archivo» keeps the old action.
- History: BPM and Tonalidad columns from the matching library track (engine adds them to `/history` rows via join: modify `server.history` to include `bpm`, `camelot` when `track_id` is set).

- [ ] **Step 1: failing tests**: `displayKey('11A')==='11A · Fa#m'`, `displayKey('8B')==='8B · Do'`; library renders `128.0` and chip `8A`; selecting 2 rows + «Analizar seleccionadas (2)» calls `analyze([p1,p2])`.
- [ ] **Step 2–4:** fail → implement → pass. Commit `feat(ui): bpm/key/lufs columns and analyze actions`.

---

### Task 12: UI — data sheet (waveform, player, tap tempo)

**Files:** Create `ui/src/components/DataSheet.tsx`, `ui/src/components/Waveform.tsx`, `ui/src/lib/tapTempo.ts`, `ui/src/components/datasheet.css`. Modify `LibraryScreen.tsx`, `HistoryScreen.tsx`, `JobRow.tsx` (button «Datos» on done downloads), `App.tsx`/`AppShell.tsx` (drop audio file on window → analyze + open sheet). Tests `ui/src/lib/tapTempo.test.ts`, `ui/src/components/DataSheet.test.tsx`.

**Interfaces — Produces:**
- `class TapTempo(now = () => performance.now())`: `tap(): number | null` (BPM after ≥ 4 taps, mean of last 8 intervals, 1 decimal), `reset()`, auto-reset when gap > 2000 ms.
- `Waveform({ data, beats, duration, position, onSeek })`: canvas, device-pixel-ratio aware; bars colored by dominant band (low → `#ff3b30`-ish red, mid → `#34c759`-ish green, high → `#5ac8fa`-ish blue, blended); beat ticks every beat, taller every 4th; playhead line; click → `onSeek(seconds)`; redraw on resize via `ResizeObserver`.
- `DataSheet({ path, onClose })`: loads `getAnalysis`; if 404 → starts `analyze([path])` and shows stage progress from jobsStore with «Cancelar»; shows facts (BPM with «confianza baja» badge if < 0.5 and «manual» badge, «8A · Lam», LUFS, pico, duración, formato, bitrate, sample rate from `getAnalysis` record + library track), `<audio src={audioUrl(path)}>` hidden with custom play/pause button and time, Waveform, Tap tempo panel (button + Space key while sheet focused; shows live BPM; «Aplicar» → `setManualBpm`), «Reanalizar» (`analyze([path], {force:true})`), «Mostrar en carpeta».

- [ ] **Step 1: failing tests**: TapTempo with fake clock taps every 500 ms ×8 → 120.0; 3 taps → null; gap 2500 ms resets; DataSheet with mocked client shows `128.0 BPM`, `8A · Lam`, `−9.1 LUFS`; «Aplicar» after taps calls `setManualBpm(path, 120)`; when `getAnalysis` 404 → `analyze` called once.
- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5:** visual check (real window capture, dark + light, 1280×800 and 1024×640) of the sheet with a real analysed song; fix what the capture shows. Commit `feat(ui): data sheet with waveform, player and tap tempo`.

---

### Task 13: UI — Armonía screen and settings

**Files:** Create `ui/src/screens/HarmonyScreen.tsx`, `ui/src/screens/harmony.css`. Modify `ui/src/components/AppShell.tsx` (nav item «Armonía», icon `Disc3`), `ui/src/App.tsx`, `ui/src/screens/SettingsScreen.tsx`, `ui/src/stores/uiStore.ts` (route `armonia`). Tests `ui/src/screens/HarmonyScreen.test.tsx`, extend `ConverterScreen.test.tsx` settings block.

**Interfaces — Consumes:** `client.harmonic`, `client.library`, `KeyChip`, `compatLabel`.

- Harmony: reference picker (searchable select of analysed library tracks) OR manual BPM input + Camelot select (24 codes with display names); tolerance segmented `±2 ±4 ±6 ±8 %` (default 6); results list: KeyChip, title/artist, BPM, «+1,2 %», compat badge; empty states «Analiza canciones de tu biblioteca para ver compatibles» and «No hay pistas compatibles con estos criterios».
- Settings: «Analizar al descargar» switch, «Notación de tonalidad en etiquetas» segmented Camelot/Musical, «Rango de BPM» two number inputs (validation message «El mínimo debe ser menor que el máximo»), «Acerca de» row with madmom model license note.

- [ ] **Step 1: failing tests**: choosing ref track calls `harmonic({ref_track: id, bpm_tolerance: 6})`; results render badges in engine order; manual mode sends `{bpm:128, camelot:'8A'}`; settings toggles send `analyze_on_download:false`, `key_notation:'musical'`; bpm_min ≥ bpm_max shows the validation message and does not save.
- [ ] **Step 2–4:** fail → implement → pass; visual check of Armonía in dark/light. Commit `feat(ui): harmony screen and analysis settings`.

---

### Task 14: E2E, packaging and acceptance

**Files:** Modify `e2e/app.spec.ts`, `build/fetch-runtime.ps1` (install `nn` group / madmom into runtime only if the winners need them), `electron-builder.yml` (if size changes nothing else). 

- [ ] **Step 1: E2E tests**: download (fake) → library row shows BPM and Tonalidad within 30 s; double-click row → data sheet shows waveform canvas and «BPM»; tap «Space» 8 times at 500 ms → «120.0»; Armonía with that track as reference shows the empty-compatibles message (single track).
- [ ] **Step 2:** run `npm run build; npx playwright test` → all pass (Phase 1 tests included).
- [ ] **Step 3:** `powershell -File build/fetch-runtime.ps1 -Force; npm run dist`; launch `dist/win-unpacked/OneForAll.exe` with restricted PATH, download a real song → library shows BPM/key; open data sheet; play audio. Record installer size.
- [ ] **Step 4:** walk spec §7 criteria 1–7, record each result in the ledger. Commit `test(e2e): analysis flows; build: runtime with analysis models`.

## Acceptance map (spec §7)

| # | Criterion | Task |
|---|---|---|
| 1 | Auto-analysis after single + playlist download, tags in Camelot | 9, 10, 14 |
| 2 | Musical notation setting | 9, 13 |
| 3 | "Analizar archivo…" → data sheet, playable | 11, 12, 14 |
| 4 | Tap tempo 120 ± 0.5, manual kept on reanalysis | 9, 12, 14 |
| 5 | Armonía ordering | 10, 13 |
| 6 | Cancel leaves no result | 9 |
| 7 | Bench report + thresholds | 5–8 |
