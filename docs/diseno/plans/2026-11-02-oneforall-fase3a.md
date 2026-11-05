# OneForAll — Fase 3a (Stems) Implementation Plan

**Goal:** Separate any library track or own file into the stems the DJ picks (Demucs htdemucs_6s + optional UVR Karaoke 2 lead/backing split), store them in a configurable folder, play, drag to a DAW, zip, and request stems straight from search.

**Architecture:** A `djengine/stems/` package with a `Separator` protocol (real Demucs, fake for tests/`--fake`), a `stems` job type (concurrency 1) whose runner writes into `tmp/<job>` and moves files on finalize, a `stems` cache table, and API routes. Electron adds a validated `startDrag` IPC. The UI adds a "Separar stems" sheet, a stems block in the download menu, a Stems section in the data sheet and settings. A gated task tries ONNX + DirectML.

**Tech Stack:** demucs (PyTorch CPU, already in runtime via `nn`), audio-separator + onnxruntime (CPU) / onnxruntime-directml, soundfile, existing FastAPI/JobManager/Electron/React.

**Spec:** `docs/diseno/specs/2026-11-02-oneforall-fase3a-stems-design.md`

## Global Constraints

- Stem ids (API) and file names: `vocals, drums, bass, guitar, piano, other`, karaoke adds `lead_vocals, backing_vocals`. Spanish labels in UI: Voz, Batería, Bajo, Guitarra, Piano, Resto, Voz principal, Coros.
- Output folder: `<stems_dir>/<render_name(name_template, meta)>/` with `stems_dir` default `<music_dir>/Stems`; collisions inside reuse the folder (same track) — file names are fixed per stem.
- Settings added: `stems_dir: str | None = None` (None → `<music_dir>/Stems`), `stems_format: Literal["wav16","wav24","flac","mp3"] = "wav16"`, `stems_backend: Literal["auto","cpu"] = "auto"`.
- Job type `stems`, concurrency 1, stages `loading_model, separating, karaoke, encoding, saving` (Spanish labels: Cargando modelo, Separando, Separando voces, Codificando, Guardando).
- Model: `htdemucs_6s`, `apply_model(split=True, overlap=0.25, shifts=0)`, 44.1 kHz stereo. Karaoke model file `UVR_MDXNET_KARA_2.onnx`.
- Packaged models: `runtime/models/torch` (set `TORCH_HOME`) and `runtime/models/uvr`.
- Errors: `UserError("model_missing", "Falta el modelo de separación y no hay conexión para descargarlo")`, `unreadable` from Phase 2.
- DirectML only if spec §6 gate passes: every stem SNR ≥ 40 dB vs CPU on 5 real tracks AND ≥ 1.5× faster.
- Analysis and Phase 1–2 behaviour unchanged; all existing tests stay green.

## Review Focus

1. Track whose title has `/ : ?` or emoji → stems folder name sanitized via `render_name`; files still found by `/stems`. Tested in Task 2.
2. Same track separated twice with different stem sets (first vocals, later drums) → second run reuses cached vocals, adds drums, folder keeps both. Tested in Task 2.
3. Source file deleted or edited after separation → `/stems` drops stale rows (file missing) and a new request recomputes. Tested in Task 2.
4. Download with `then_stems` where the download fails → no stems job queued; stems job failing never marks the download failed. Tested in Task 5.
5. Drag request for a path that is not a registered stem (or a non-audio file) → refused in main, nothing dragged. Tested in Task 6.

---

### Task 1: Settings, stem names, cache store

**Files:** Modify `engine/djengine/settings.py`, `engine/pyproject.toml` (add `demucs`, `audio-separator`, `onnxruntime` to extra `nn`). Create `engine/djengine/stems/__init__.py`, `engine/djengine/stems/names.py`, `engine/djengine/stems/store.py`. Test `engine/tests/stems/test_store.py`.

**Interfaces — Produces:**
- `names.STEMS = ("vocals","drums","bass","guitar","piano","other")`, `KARAOKE = ("lead_vocals","backing_vocals")`, `LABELS_ES: dict[str,str]`, `stems_folder(settings, meta: dict) -> Path`, `ext_for(fmt) -> str`.
- `StemsStore(db_path)`: `get(path) -> dict[str, Path]` (only rows whose source size+mtime match and whose stem file exists; stale rows deleted), `add(path, stem, file: Path, model: str)`, `folder_for(path) -> Path | None`, `is_stem_file(file) -> bool`.

- [ ] **Step 1:** `uv add --optional nn demucs audio-separator onnxruntime`; `uv sync --extra nn`; `python -c "import demucs, audio_separator"` exits 0.
- [ ] **Step 2: failing tests** — settings defaults (`stems_dir is None`, `stems_format=="wav16"`, `stems_backend=="auto"`); `stems_folder` → `<music>/Stems/Quevedo - LA GRACIOSA` and with title `AC/DC: Live?` → no illegal chars; store add/get round trip; editing source mtime → `get` returns `{}` and rows deleted; deleted stem file → dropped; `is_stem_file` true only for registered files.
- [ ] **Step 3–4:** fail → implement → pass (`py -m uv run pytest tests/stems -q`). Commit `feat(stems): settings, names and cache store`.

---

### Task 2: Separator protocol, fake separator, runner

**Files:** Create `engine/djengine/stems/separate.py` (protocol + `FakeSeparator`), `engine/djengine/stems/runner.py`. Test `engine/tests/stems/test_runner.py`.

**Interfaces — Produces:**
- `class Separator(Protocol)`: `name: str`; `separate(audio: np.ndarray, sr: int, progress: Callable[[float], None], cancelled: Callable[[], bool]) -> dict[str, np.ndarray]` (all 6 stems, shape `(2, n)`).
- `FakeSeparator`: deterministic filters (bass = lowpass 150 Hz, drums = highpass 5 kHz, vocals = band 300–3k, others = scaled copies) in ≤ 0.5 s; calls `progress` 5 times.
- `get_separator(svc) -> Separator` (fake when `svc.fake` or env `ONEFORALL_FAKE_STEMS=1`, else Demucs from Task 3).
- `make_stems_runner(svc, path: Path, wanted: list[str], karaoke: bool) -> Runner`: cache hit for all wanted → return immediately; decode 44.1 kHz stereo (Phase 2 `decode`); stage `separating` maps progress 5–80 %; check cancel between chunks; karaoke (Task 4) when requested; `encoding` writes each wanted stem to `tmp/<job>/<stem>.<ext>` in `settings.stems_format` (soundfile for wav/flac, ffmpeg for mp3 320k); `begin_finalize`; `os.replace` into `stems_folder`; `store.add`. Returns `{"path": str(path), "folder": str, "stems": {stem: file}}`.

- [ ] **Step 1: failing tests** (fake separator, real files): wanted `["vocals","drums","bass"]` → exactly 3 files `vocals.wav drums.wav bass.wav` in the folder, 16-bit 44.1 kHz; formats wav24/flac/mp3 readable by mutagen with expected subtype/codec; second run for `["vocals"]` is a cache hit (separator call counter unchanged); later `["drums","guitar"]` adds `guitar.wav`, keeps others; cancel during `separating` → folder untouched, `tmp/` empty; illegal-char title folder; source edited → recompute.
- [ ] **Step 2–4:** fail → implement → pass. Commit `feat(stems): runner with cache, formats and clean cancel`.

---

### Task 3: Real Demucs separator and models

**Files:** Create `engine/djengine/stems/demucs_sep.py`, `engine/djengine/stems/models.py`. Test `engine/tests/stems/test_demucs_slow.py` (marker `slow`, deselected by default: add `slow` to `addopts` exclusion).

**Interfaces — Produces:** `DemucsSeparator(name="htdemucs_6s", device="cpu")` implementing `Separator`: lazy model load (`demucs.pretrained.get_model`) under a lock; calls `demucs.apply.apply_model(model, x, split=True, overlap=0.25, shifts=0, progress=False)` per 60 s block of the song (blocks joined with a 1 s linear cross-fade) so `progress` and `cancelled` run between blocks. `models.ensure_torch_home()` sets `TORCH_HOME` to `ONEFORALL_MODELS/torch` when that dir exists; download failures map to `model_missing`.

- [ ] **Step 1: failing slow test:** 10 s synthetic mix (clicks + 55 Hz bass tone) → output keys == STEMS, drums carries > 50 % of the click energy (high-pass band), bass carries > 50 % of the < 120 Hz energy; and `model_missing` is raised when model download is forced to fail (monkeypatch `get_model` to raise `urllib.error.URLError`).
- [ ] **Step 2–4:** fail → implement → pass (`pytest -m slow tests/stems/test_demucs_slow.py`). Record seconds per 10 s of audio in the ledger. Commit `feat(stems): demucs htdemucs_6s separator`.

---

### Task 4: Karaoke split (lead / backing)

**Files:** Create `engine/djengine/stems/karaoke.py`. Test `engine/tests/stems/test_karaoke.py`.

**Interfaces — Produces:** `split_vocals(vocals: np.ndarray, sr: int, workdir: Path, provider: str) -> tuple[np.ndarray, np.ndarray]` using `audio_separator.separator.Separator(model_file_dir=<models>/uvr, output_dir=workdir)` with `UVR_MDXNET_KARA_2.onnx`; `FakeKaraoke` for tests (lead = mid channel, backing = side). Runner uses fake when separator is fake.

- [ ] **Step 1: failing tests:** fake path → runner with `karaoke=True` writes `lead_vocals` and `backing_vocals` (and `vocals`); slow test with the real model on 10 s of a stereo signal → two arrays with the input's length ± 1 %.
- [ ] **Step 2–4:** fail → implement → pass. Commit `feat(stems): lead/backing vocal split`.

---

### Task 5: API, download-then-stems, fake mode

**Files:** Modify `engine/djengine/server.py`, `engine/djengine/pipelines.py`, `engine/djengine/jobs` concurrency map. Test `engine/tests/test_api_stems.py`.

**Interfaces — Produces:**
- `POST /jobs {"type":"stems","paths":[...],"stems":[...],"karaoke":false}` → `{"jobs":[...]}`; 422 for unknown stem ids or empty list; karaoke implies vocals. Payload kept for retry. Concurrency `"stems": 1`.
- `DownloadRequest.then_stems: {"stems": list[str], "karaoke": bool} | None` → after a successful download, `submit_stems(svc, final, ...)` (top-level job).
- `GET /stems?path=` → `{"folder": str|None, "stems":[{"stem","file","size_bytes"}]}`.
- `POST /stems/zip {"path"}` → `{"zip": str}` at `<folder>/<folder name> (stems).zip` (overwrite).
- `/audio` also allows `store.is_stem_file`.
- `GET /library` rows gain `has_stems: bool`.

- [ ] **Step 1: failing tests:** stems job end-to-end (fake) → `/stems` lists 3; zip contains exactly those 3 names; unknown stem → 422; `then_stems` with download success → a `stems` job `done`; with the fake private track (download fails) → no stems job; cancelling the stems job leaves the download `done`; `/audio` 206 for a stem file, 403 for a non-stem wav next to it; `/library` `has_stems` true after separation.
- [ ] **Step 2–4:** fail → implement → pass (full engine suite). Commit `feat(engine): stems api, download-then-stems, zip`.

---

### Task 6: Electron drag to DAW

**Files:** Modify `app/main/index.ts`, `app/preload/index.ts`, `ui/src/types/oneforall.d.ts`. Create `app/main/drag.ts`, `app/main/drag.test.ts`, `build/resources/drag.png` (32 px icon).

**Interfaces — Produces:** `isDraggableStem(file: string, allowed: Set<string>): boolean` (normalized path in allowed set AND audio extension AND exists); IPC `drag:allow(files: string[])` (renderer registers the files it got from `/stems`) and `drag:start(file)` → `event.sender.startDrag({ file, icon })` only if allowed. Preload exposes `allowDrag(files)`, `startDrag(file)`.

- [ ] **Step 1: failing tests:** `isDraggableStem` true for an allowed existing `.wav`; false for not-allowed path, `.exe`, missing file, `..`-traversal of an allowed path.
- [ ] **Step 2–4:** fail → implement → pass (`npx vitest run app`). Commit `feat(app): drag stems to other apps`.

---

### Task 7: UI — client, "Separar stems" sheet, library and history

**Files:** Modify `ui/src/lib/types.ts`, `ui/src/lib/engineClient.ts`, `ui/src/screens/LibraryScreen.tsx`, `ui/src/screens/HistoryScreen.tsx`, `ui/src/components/JobRow.tsx` (stage labels). Create `ui/src/components/StemsSheet.tsx`, `ui/src/lib/stems.ts`. Tests `ui/src/components/StemsSheet.test.tsx`.

**Interfaces — Produces:** client `separate(paths, stems, karaoke)`, `getStems(path)`, `zipStems(path)`; `stems.ts`: `STEM_IDS`, `STEM_LABEL`, `estimateSeconds(durationS, history?: number[]) -> number` (mean seconds-per-audio-second of the last 5 stems jobs, else 0.4). `StemsSheet({ paths, durationS, onClose })`: 6 checkboxes with Voz, Batería, Bajo, Guitarra pre-checked (spec: "las 4 primeras"), switch "Separar voz principal y coros", text «≈ N min en este equipo», button «Separar» disabled with 0 checked. `uiStore.openStems(paths: string[])` + host in App.

- [ ] **Step 1: failing tests:** default checked = Voz, Batería, Bajo, Guitarra; unchecking all disables «Separar»; karaoke on → `separate(paths, ['vocals',...], true)`; estimate text for a 240 s track with no history «≈ 2 min»; library toolbar «Separar stems (N)» with selection and column icon for `has_stems`.
- [ ] **Step 2–4:** fail → implement → pass. Commit `feat(ui): separate-stems sheet and library actions`.

---

### Task 8: UI — search stems block, data sheet Stems section, settings

**Files:** Modify `ui/src/components/FormatMenu.tsx`, `ui/src/components/DownloadButton.tsx`, `ui/src/screens/SearchScreen.tsx`, `ui/src/components/DataSheet.tsx`, `ui/src/screens/SettingsScreen.tsx`. Create `ui/src/components/StemsSection.tsx`. Tests `ui/src/components/StemsSection.test.tsx`, extend `SearchScreen.test.tsx`, settings test.

**Interfaces — Consumes:** Task 5 API, Task 6 preload, Task 7 sheet.
- Download menu block «Stems»: «Solo voz», «Solo batería», «Solo bajo», «Todos los stems», «Elegir…» (opens StemsSheet in "after download" mode) → `download({..., then_stems})`.
- `StemsSection({ path })`: rows (icon, label, play/pause through one shared `<audio>`, size, drag handle `draggable` → `onDragStart` preventDefault + `window.oneforall.startDrag(file)`), «Mostrar carpeta», «Exportar zip»; registers files with `allowDrag`; shows progress + Cancelar for a running stems job of this path; empty state «Aún no hay stems» + «Separar stems…».
- Settings section «Stems»: carpeta (Cambiar…), formato (WAV 16 bits / WAV 24 bits / FLAC / MP3 320), cálculo (Automático / Solo CPU) + «Usando: CPU» / «Usando: GPU (DirectML)» from `GET /stems/backend`.

- [ ] **Step 1: failing tests:** «Solo voz» → `download` called with `then_stems: {stems:['vocals'], karaoke:false}`; StemsSection renders 3 rows from `getStems`, calls `allowDrag` with the 3 files, «Exportar zip» → `zipStems(path)`; settings writes `stems_format:'flac'`, `stems_backend:'cpu'`.
- [ ] **Step 2–4:** fail → implement → pass; visual check (real capture, dark + light, 1280 and 1024) of data sheet with stems and the download menu. Commit `feat(ui): stems in search, data sheet and settings`.

---

### Task 9: ONNX + DirectML acceleration (gated)

**Files:** Create `engine/djengine/stems/accel.py`, `engine/bench/stems_accel.py`, `docs/bench/2026-11-fase3a-accel.md`. Add `GET /stems/backend` in `server.py`. Test `engine/tests/stems/test_accel.py`.

**Interfaces — Produces:** `backend(settings) -> Literal["directml","cpu"]` (directml only if `stems_backend=="auto"` AND `models/onnx/htdemucs_6s.onnx` exists AND `accel_validated.json` in the same dir says `passed: true` AND onnxruntime lists `DmlExecutionProvider`); `OnnxDemucsSeparator` (same Separator protocol: STFT/iSTFT/mask in torch CPU, network core via onnxruntime session).

- [ ] **Step 1: tests (always run):** `backend` returns `cpu` when any of the four conditions fails (parametrized); `/stems/backend` returns `{"backend":"cpu"}` in tests.
- [ ] **Step 2:** export: wrap the htdemucs core (everything between `_spec`/`_magnitude` output and `_mask` input, plus the time branch) in an `nn.Module`, `torch.onnx.export` opset 17 with fixed segment length (the model's `segment` × 44100); if export fails, record the error in the report and skip to Step 5 with `passed: false`.
- [ ] **Step 3:** `python -m bench.stems_accel` on 5 library tracks: per-stem SNR vs CPU PyTorch and speed ratio; writes the report and `accel_validated.json`.
- [ ] **Step 4: gate:** passes only if every stem ≥ 40 dB and speed ≥ 1.5×. Ledger the numbers.
- [ ] **Step 5:** commit `feat(stems): onnx/directml acceleration with validation gate` (code + report; model artefacts git-ignored, copied into runtime only if passed).

---

### Task 10: E2E, packaging, acceptance

**Files:** Modify `e2e/app.spec.ts`, `build/fetch-runtime.ps1`, `app/main/index.ts` (`TORCH_HOME` env), `README.md` (licences: Demucs MIT, audio-separator MIT, UVR model).

- [ ] **Step 1: E2E (fake engine + fake separator):** library → «Separar stems» → 3 stems → data sheet lists them → «Exportar zip» → zip file exists in the stems folder.
- [ ] **Step 2:** `fetch-runtime.ps1`: pre-download `htdemucs_6s` into `runtime/models/torch` and `UVR_MDXNET_KARA_2.onnx` into `runtime/models/uvr`; import check runs `DemucsSeparator` on 2 s of silence. `npm run dist`.
- [ ] **Step 3:** packaged run (PATH = System32) on a real song: separate vocals+drums+bass, time it, play a stem, drag a stem to Explorer (manual check noted), zip.
- [ ] **Step 4:** all suites green; walk spec §7 criteria 1–7 into the ledger. Commit `test(e2e): stems flows; build: runtime with separation models`.

## Acceptance map (spec §7)

| # | Criterion | Task |
|---|---|---|
| 1 | Voice+drums+bass → exactly 3 files, ~2 min CPU | 2, 3, 10 |
| 2 | Lead/backing split | 4 |
| 3 | Search «Solo voz» | 5, 8 |
| 4 | Cancel clean, no second instance | 2, 5 (single-instance lock from Phase 1) |
| 5 | Play, drag, zip | 5, 6, 8, 10 |
| 6 | Folder/format settings apply | 1, 2, 8 |
| 7 | Accel report; DirectML only if gate passed | 9 |
