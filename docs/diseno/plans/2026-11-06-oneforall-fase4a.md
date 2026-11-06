# OneForAll — Fase 4a (DJ Tools) Implementation Plan

**Goal:** Ship four DJ-preparation tools:
- an editable fixed beat grid;
- auto-detected, editable sections;
- "change BPM/key" copies of a file;
- export of BPM, key, grid and section cues to Rekordbox XML, VirtualDJ and Serato.

**Architecture:**
- **Data:** the analysis sidecar gains `grid`/`grid_auto` (anchor + BPM) and `sections`/`sections_auto`. The existing `beats` list is always derived from the grid, so the waveform, mixer and metronome keep working unchanged.
- **Engine packages:** `djengine/tools/` (grid, sections, retempo job) and `djengine/export/` (one pure function per DJ program, plus a `dj_export` job).
- **UI:** a grid mode and section bands in the data sheet, a "Cambiar BPM y tono" sheet, and an "Exportar a…" menu in the library.

**Tech Stack:** librosa/numpy (already in the engine), the bundled ffmpeg (`rubberband`), mutagen (ID3 GEOB, Vorbis comments, MP4 freeform atoms), `xml.etree`, psutil, React.

**Spec:** `docs/diseno/specs/2026-11-06-oneforall-fase4a-herramientas-dj-design.md`

## Global Constraints

- **Grid:**
  - `{anchor: float (s, first "1"), bpm: float, source: "auto"|"manual", meter: 4}`.
  - `beats(grid, duration)` = every `anchor + k·60/bpm` inside `[0, duration)`, including k < 0.
- **Sections:** `{start, end, label, source}`.
  - Labels exactly: `Intro`, `Verso`, `Subida`, `Estribillo/Drop`, `Bajón`, `Outro`.
  - Minimum 8 bars; at most 16 sections; boundaries on 8-bar multiples from the anchor.
- **Section colours (RGB):** Intro (142,142,147), Verso (10,132,255), Subida (255,214,10), Estribillo/Drop (255,69,58), Bajón (191,90,242), Outro (99,99,102).
- **Analysis version:** `ANALYSIS_VERSION = 2`. Version-1 sidecars are converted when read: grid from the first beat, `sections: []`, `needs_reanalysis: true`.
- **Manual edits survive re-analysis:** a grid or sections with `source: "manual"` is kept unless the user resets it ("Volver al automático").
- **Retempo:**
  - target BPM within [0.5, 1.5] × the original BPM; semis −12…+12;
  - filter `rubberband=tempo=<ratio>:pitch=<2^(semis/12)>:pitchq=quality:transients=mixed`;
  - name `«<stem> (124 BPM, 9A).<ext>»`, where a part is left out when unchanged (`(124 BPM)` or `(9A)`), and the BPM is printed with `:g` on the value rounded to 0.1;
  - the default format follows the original (wav→wav16, flac→flac, mp3→mp3 320; anything else → flac).
- **Cues:** one memory cue per section, named with its label; the first 8 sections are also hot cues 0–7 (A–H), with the section colour.
- **Key in exports:** English musical notation from tonic and mode: `Am`, `F#`, `C#m`.
- **Times:** seconds with 3 decimals in XML; integer milliseconds in Serato.
- **UI copy (Spanish):**
  - Rejilla, El 1 aquí, Volver al automático, Cambiar BPM y tono, Exportar a…, Analiza primero, Reanaliza para detectar secciones;
  - Cierra VirtualDJ para exportar, No se pudo leer la base de datos de VirtualDJ, Formato no compatible con Serato, Archivo en uso, Sin analizar, Archivo no encontrado.
- **No new Python or npm dependencies.** All existing suites stay green.

## Review Focus

1. **A version-1 analysis (opened before this phase):**
   - the data sheet shows the converted grid, no sections and "Reanaliza para detectar secciones";
   - exporting it works, with the grid and no cues.
   - Tested in Task 3 and Task 8.
2. **Paths with accents, spaces, `&`, `#`, `%`:** the Rekordbox `Location` is URL-encoded and decodes back to the exact path, and the VirtualDJ `FilePath` is XML-escaped. Tested in Tasks 5 and 6.
3. **Exporting the same track twice:**
   - the VirtualDJ entry is replaced, not duplicated;
   - Serato tags are replaced, not appended;
   - Rekordbox is overwritten atomically.
   - Tested in Tasks 5, 6 and 7.
4. **A target name that already exists, or retempo of a retempo'd file:** `unique_path` adds `(1)`, and a BPM outside the range gives 422. Tested in Task 4.
5. **A very short (< 8 bars) or silent track, or one with no detected beats:** the sections are `[]` or a single section, the grid falls back to anchor 0, and nothing crashes. Tested in Tasks 1 and 2.

---

### Task 1: Grid model, estimation and grid API

**Files:**
- Create: `engine/djengine/tools/__init__.py`, `engine/djengine/tools/grid.py`
- Modify: `engine/djengine/analysis/store.py` (grid helpers; the existing `set_beats_from_bpm` becomes grid-based), `engine/djengine/analysis/runner.py` (store `grid`/`grid_auto`), `engine/djengine/server.py` (`PUT /analysis/grid`; `GET /analysis` returns the grid)
- Test: `engine/tests/tools/__init__.py`, `engine/tests/tools/test_grid.py`

**Interfaces:**
- Produces:
  - `@dataclass Grid(anchor: float, bpm: float, source: str = "auto", meter: int = 4)` with `to_dict()` and `from_dict(d)`.
  - `beats(grid: Grid, duration: float) -> list[float]` (values rounded to 4 decimals).
  - `grid_from_beats(beats: list[float], bpm: float) -> Grid`: phase = circular mean of `b mod period`, anchor = first grid point ≥ 0; with no beats, anchor 0.
  - `estimate_grid(y: np.ndarray, sr: int, bpm: float, beats: list[float]) -> Grid`: phase from `grid_from_beats`. The anchor is the grid point, among the first 8, whose low-band onset strength (mel bands ≤ 150 Hz) is highest.
  - `edit_grid(grid: Grid, *, anchor=None, bpm=None, shift_ms=None, shift_beats=None, scale=None) -> Grid`. It always returns `source="manual"`. With `scale`, the BPM is multiplied by 0.5 or 2 and the anchor is kept.
  - `AnalysisStore.get_grid(path) -> Grid | None`: reads `sidecar["grid"]`, or converts a version-1 sidecar with `grid_from_beats(beats, record.bpm)`.
  - `AnalysisStore.save_grid(path, grid: Grid) -> None`: writes `sidecar["grid"]` and also rewrites `sidecar["beats"] = beats(grid, duration)`.
  - `PUT /analysis/grid {path, anchor?, bpm?, shift_ms?, shift_beats?, scale?: 0.5|2, reset?: bool}` → `{"grid": {...}}`. It answers 404 when not analysed and 409 when the analysis is stale. A BPM change also updates the record (manual), the BPM tag and the library row, the same way `PUT /analysis/bpm` does.
  - The existing `PUT /analysis/bpm` now calls `edit_grid(bpm=...)` (the anchor is kept) instead of `set_beats_from_bpm`. Remove `set_beats_from_bpm` and adapt its test to `save_grid`.

- [ ] **Step 1: Write failing tests:**
  - `test_beats_from_anchor_includes_before`: `beats(Grid(1.0, 120), 3.0) == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]`.
  - `test_grid_from_beats_phase`: beats `[0.26, 0.74, 1.25, 1.76]` at 120 → anchor ≈ 0.25 (±0.01).
  - `test_grid_from_no_beats`: anchor 0.0.
  - `test_estimate_grid_finds_downbeat`: 44.1 kHz synthetic signal, clicks every 0.5 s plus a 60 Hz thump on every 4th beat starting at 1.0 s → anchor ≈ 1.0 (±0.02).
  - `test_edit_grid_ops`:
    - `shift_ms=10` gives anchor +0.010;
    - `shift_beats=-1` gives anchor −0.5 at 120 BPM;
    - `scale=2` gives 240 BPM with the anchor unchanged;
    - every result has source manual.
  - `test_v1_sidecar_converted`: save a version-1 sidecar `{"beats": [0.5, 1.0], ...}`, then `get_grid` returns anchor 0.5.
  - `test_put_grid_api`:
    - an anchor of 2.0 is saved and the sidecar `beats` contains 2.0;
    - a stale file gives 409;
    - `reset` brings back `grid_auto`;
    - a BPM change makes the record source manual.
  - `test_reanalysis_keeps_manual_grid`: after a manual anchor and `force=True`, the anchor is unchanged.
- [ ] **Step 2:** `py -m uv run pytest tests/tools/test_grid.py -q` fails.
- [ ] **Step 3: Implement.**
  - In `runner._analyse`, compute `grid_auto = estimate_grid(y, SR, bpm, tempo.beats)` after the tempo.
  - In `run`, keep the previous `grid` if its `source` is manual and `reset_bpm` is false. Otherwise use `grid_auto` with the final BPM (manual BPM kept as today).
  - Save `{"grid", "grid_auto", "beats": beats(grid, duration), ...}`.
- [ ] **Step 4:** Grid tests pass, and the full engine suite passes.
- [ ] **Step 5:** Commit `feat(grid): fixed beat grid model, estimation and edit API`.

### Task 2: Section detection (pure)

**Files:**
- Create: `engine/djengine/tools/sections.py`
- Test: `engine/tests/tools/test_sections.py`

**Interfaces:**
- Consumes: `Grid`, `beats` (Task 1).
- Produces:
  - `@dataclass Section(start: float, end: float, label: str, source: str = "auto")` with `to_dict` and `from_dict`.
  - `LABELS`.
  - `COLORS: dict[str, tuple[int, int, int]]`, with the values from Global Constraints.
  - `detect_sections(y: np.ndarray, sr: int, grid: Grid, duration: float) -> list[Section]`.
  - `label_sections(energies: list[float]) -> list[str]`, which applies the spec §4 rules in this order:
    1. the first section is Intro if its energy is below the median;
    2. the last section is Outro in the same case;
    3. sections with energy above the 70th percentile are Estribillo/Drop;
    4. a low-energy section after a high one is Bajón;
    5. a section rising in energy just before a high one is Subida;
    6. the rest is Verso.

- [ ] **Step 1: Write failing tests:**
  - `test_label_rules`: energies `[0.2, 0.5, 0.7, 1.0, 0.3, 0.9, 0.1]` → `["Intro", "Verso", "Subida", "Estribillo/Drop", "Bajón", "Estribillo/Drop", "Outro"]`.
  - `test_detects_synthetic_structure`:
    - 128 BPM and anchor 0;
    - 8 bars of quiet hi-hat, 16 bars of loud kick + bass + chords, 8 bars of pads, 16 bars loud, 8 bars quiet;
    - expect boundaries at bars 8, 24, 32, 48 (±1 bar);
    - expect labels Intro, Estribillo/Drop, Bajón, Estribillo/Drop, Outro.
  - `test_boundaries_on_8_bar_multiples`: every `start` is a multiple of 8 bars from the anchor, within 1 ms.
  - `test_short_or_silent_track`: a 10 s tone gives a single section or `[]`, and silence gives `[]`, with no exception.
  - `test_at_most_16_sections`: noise that changes every 8 bars for 300 bars gives 16 sections or fewer.
- [ ] **Step 2:** The tests fail.
- [ ] **Step 3: Implement.**
  - Beat-synchronous features: RMS, 13 MFCC and 12 chroma (`librosa.util.sync` on the grid beats), z-scored.
  - Aggregate per bar, then build the self-similarity matrix and a Foote checkerboard novelty with a kernel of 8 bars.
  - Peaks become candidate boundaries at multiples of 8 bars. Keep the strongest, at least 8 bars apart, at most 15 boundaries.
  - Energy for the labels = mean RMS of each section, normalised to its maximum.
- [ ] **Step 4:** The tests pass.
- [ ] **Step 5:** Commit `feat(sections): energy and novelty sections on 8-bar phrases`.

### Task 3: Sections in the analysis and the sections API

**Files:**
- Modify: `engine/djengine/analysis/config.py` (`ANALYSIS_VERSION = 2`), `engine/djengine/analysis/runner.py`, `engine/djengine/analysis/store.py`, `engine/djengine/server.py`
- Test: `engine/tests/tools/test_sections_api.py`

**Interfaces:**
- Consumes: `detect_sections`, `Section` (Task 2); `Grid`, `get_grid` (Task 1).
- Produces:
  - Sidecar keys `sections` and `sections_auto` (lists of dicts), and `needs_reanalysis: bool` (true for version-1 records).
  - `AnalysisStore.get_sections(path) -> list[Section]`.
  - `AnalysisStore.save_sections(path, sections) -> None`.
  - `PUT /analysis/sections {path, sections: [{start, end, label}]} | {path, reset: true}` → `{"sections": [...]}`.
    - 422 unless the sections are sorted, non-overlapping, inside `[0, duration]`, each `end > start` and each label in `LABELS`.
    - Saved sections are marked manual; `reset` brings back `sections_auto`.
  - `GET /analysis` sidecar includes `grid`, `sections` and `needs_reanalysis`.

- [ ] **Step 1: Write failing tests:**
  - `test_analysis_stores_sections`: a click track analysed with `force` gives a list in `sections` (it may be short) and `needs_reanalysis` false.
  - `test_v1_record_flags_reanalysis`: insert a version-1 record and sidecar; `GET /analysis` returns `needs_reanalysis` true, `sections` `[]` and a grid with an anchor.
  - `test_put_sections_validation`: overlapping sections give 422; an unknown label gives 422; a valid list gives 200 with source manual.
  - `test_reanalysis_keeps_manual_sections`, and `reset` brings back the auto sections.
- [ ] **Step 2:** The tests fail.
- [ ] **Step 3: Implement.**
  - `_analyse` takes `grid_for_sections: Grid | None`, which is the kept manual grid when there is one.
  - It returns a small dataclass `AnalysisParts` (tempo, key, lufs, peak, wf, duration, grid_auto, sections_auto) instead of the current tuple.
- [ ] **Step 4:** The tests pass, and so does the full engine suite. Existing analysis tests that check `version == 1` get updated to 2.
- [ ] **Step 5:** Commit `feat(sections): sections in the analysis, edit API, analysis v2`.

### Task 4: `retempo` job

**Files:**
- Create: `engine/djengine/tools/retempo.py`
- Modify: `engine/djengine/analysis/camelot.py` (add `camelot_shift(code: str, semis: int) -> str`, where +1 semitone is +7 on the wheel), `engine/djengine/server.py` (`RetempoJobBody` in `JobBody`; concurrency `"retempo": 1`)
- Test: `engine/tests/tools/test_retempo.py`

**Interfaces:**
- Consumes: `Grid`, `get_grid`, `save_grid` (Task 1); `get_sections`, `save_sections`, `Section` (Task 3); `ffmpeg_error`, `_commit`, `unique_path`, `read_tags`, `write_tags`, `set_bpm_key`, `measure`, `compute`, `decode`.
- Produces:
  - `RetempoJobBody`: `type: Literal["retempo"]`, `path: str`, `bpm: float`, `semis: int (-12..12)`, `format: Literal["wav16","wav24","flac","mp3"] | None`.
  - `make_retempo_runner(svc, path, bpm, semis, fmt) -> Runner`, with result `{"path": str}`. Stages `rendering` and `analysing`.
  - `retempo_name(stem: str, src_bpm: float, bpm: float, src_camelot: str | None, semis: int) -> str` (without extension).

- [ ] **Step 1: Write failing tests:**
  - `test_retempo_name`:
    - `("Song", 128, 124, "8A", 2)` → `"Song (124 BPM, 10A)"`;
    - `("Song", 128, 128, "8A", 1)` → `"Song (3A)"`;
    - `("Song", 128, 124.25, None, 0)` → `"Song (124.2 BPM)"`.
  - `test_camelot_shift`: `("8A", 2) == "10A"`, `("8A", -1) == "1A"`.
  - `test_retempo_render_and_scaled_analysis`:
    - input: a 4 s 440 Hz sine analysed with bpm 120 (stored record), a manual grid with anchor 1.0 and the section `[0, 4, "Intro"]`;
    - retempo to 60 BPM and +12;
    - the output lasts ≈ 8.0 s and its dominant frequency is ≈ 880 Hz (±1 %);
    - the new record has bpm 60, camelot shifted, grid anchor 2.0 and sections `[0, 8]`;
    - the library has a new row for that path.
  - `test_retempo_out_of_range`: a BPM of 2.0 × the original gives a job error `bad_request`; through the API it is 422.
  - `test_retempo_not_analysed`: the job fails with "Analiza primero".
  - `test_retempo_name_collision`: running it twice gives the second name with ` (1)`.
  - `test_retempo_cancel_leaves_no_file`: same slowdown seam as the mixer export (`_extra_args`).
- [ ] **Step 2:** The tests fail.
- [ ] **Step 3: Implement.**
  - Follow `mixer/export.py` for the ffmpeg run, progress, commit and history (action `"retempo"`).
  - Light analysis of the output:
    - decode, then `measure` and `compute`;
    - write an `AnalysisRecord` with bpm = target, source manual, tonic/mode from `from_camelot(camelot_shift(...))`, confidences copied, version 2;
    - sidecar grid = `Grid(anchor / ratio, target, "manual")`, sections scaled by `1/ratio`.
  - Tags: copy them from the original with `read_tags` / `write_tags`, then `set_bpm_key` with the new values (key in the notation from settings).
- [ ] **Step 4:** The tests pass, and so does the full engine suite.
- [ ] **Step 5:** Commit `feat(tools): change BPM and key into a new analysed file`.

### Task 5: Export model and Rekordbox XML

**Files:**
- Create: `engine/djengine/export/__init__.py`, `engine/djengine/export/model.py`, `engine/djengine/export/rekordbox.py`
- Modify: `engine/djengine/library.py` (`list_playlists() -> list[tuple[int, str]]` and `playlist_track_ids(playlist_id) -> list[int]`)
- Test: `engine/tests/export/__init__.py`, `engine/tests/export/test_model.py`, `engine/tests/export/test_rekordbox.py`, `engine/tests/export/golden_rekordbox.xml`

**Interfaces:**
- Consumes: `get_grid` (Task 1), `get_sections`, `COLORS` (Tasks 2–3).
- Produces:
  - `@dataclass Cue(start: float, name: str, color: tuple[int, int, int], hot: int | None)`.
  - `@dataclass ExportTrack(id: int, path: str, title: str, artist: str, album: str, duration: float, size: int, bpm: float, key: str, anchor: float, cues: list[Cue], kind: str)`, where `kind` is `"MP3 File"`, `"WAV File"`, `"FLAC File"`, `"M4A File"` or `"AIFF File"`.
  - `english_key(tonic, mode) -> str`.
  - `collect(svc, track_ids: list[int] | None) -> tuple[list[ExportTrack], list[dict]]`, where the skipped entries are `{title, reason}` with reasons "Sin analizar" and "Archivo no encontrado".
  - `cues_for(sections) -> list[Cue]`: one memory cue per section, plus `hot` 0–7 for the first 8.
  - `rekordbox_xml(tracks: list[ExportTrack], playlists: list[tuple[str, list[int]]]) -> str`.
  - `mp3_decoder_offset(path) -> float`: the LAME/Xing encoder delay plus 529 samples, divided by the sample rate, when a LAME header is present; 0.0 otherwise.
  - `write_rekordbox(path_out: Path, xml: str) -> None`: atomic, through a `~oneforall-*.part` file.

- [ ] **Step 1: Write failing tests:**
  - `test_english_key`: `("A", "minor") == "Am"` and `("F#", "major") == "F#"`.
  - `test_cues_for`: 10 sections give 10 memory cues, the first 8 with `hot` 0–7 and the colour of their label.
  - `test_collect_skips`: an unanalysed track is reported as "Sin analizar" and a missing file as "Archivo no encontrado".
  - `test_rekordbox_golden`: 2 tracks, one with a path containing `Canción & Co #1 100%.mp3`; the output equals the golden file byte for byte.
  - `test_location_round_trip`: `unquote` of the `Location` after `file://localhost/` gives back the exact path, with forward slashes.
  - `test_rekordbox_parses`: `ElementTree.fromstring` works; `TEMPO Inizio` equals the anchor plus the MP3 offset; `POSITION_MARK` has `Num="-1"` for memory cues and `0`–`7` for hot cues.
  - `test_mp3_offset_without_lame_header_is_zero`.
  - `test_write_atomic_overwrite`: writing twice leaves a single, complete file.
- [ ] **Step 2:** The tests fail.
- [ ] **Step 3: Implement.**
  - Generate the golden file once from the implementation, check it by hand against the documented structure (DJ_PLAYLISTS / PRODUCT / COLLECTION / PLAYLISTS ROOT → NODE "OneForAll"), and commit it.
  - `PRODUCT Name="OneForAll" Version="0.1.0" Company="OneForAll"`.
  - Attribute order: TrackID, Name, Artist, Album, Kind, Size, TotalTime, AverageBpm, Tonality, Location.
- [ ] **Step 4:** The tests pass.
- [ ] **Step 5:** Commit `feat(export): export model and Rekordbox XML`.

### Task 6: VirtualDJ database

**Files:**
- Create: `engine/djengine/export/virtualdj.py`
- Test: `engine/tests/export/test_virtualdj.py`

**Interfaces:**
- Consumes: `ExportTrack`, `Cue` (Task 5).
- Produces:
  - `database_for(track_path: str) -> Path`. A track on the system drive (`%SystemDrive%`) maps to `<Documents>\VirtualDJ\database.xml`, with `<Documents>` taken from `SHGetKnownFolderPath(FOLDERID_Documents)` via ctypes (fallback `~/Documents`). Any other drive maps to `<drive>:\VirtualDJ\database.xml`.
  - `virtualdj_running() -> bool`: psutil names `virtualdj.exe`, `virtualdj8.exe`, `virtualdj_pc.exe`, case-insensitive.
  - `merge_database(xml_text: str | None, tracks: list[ExportTrack]) -> str`. For each track it replaces or creates `<Song FilePath FileSize>` with:
    - `Tags Author Title Album`;
    - `Infos SongLength`;
    - `Scan Version="801" Bpm=<60/bpm, 6 decimals> Key=<english key>`;
    - `Poi Pos=<anchor> Type="beatgrid"`;
    - `Poi Name Pos Num=<1-based> Type="cue"`.
    It keeps every other `Song` and every attribute or child it does not set. It raises `UserError("bad_request", "No se pudo leer la base de datos de VirtualDJ")` when the text cannot be parsed.
  - `write_virtualdj(tracks) -> list[Path]`: groups by database, raises `UserError("busy", "Cierra VirtualDJ para exportar")` when it is running, writes a backup `database.xml.bak-<YYYYmmdd-HHMMSS>` when the file exists, and writes atomically. A missing `VirtualDJ` folder means those tracks are skipped with "No se encontró la carpeta de VirtualDJ".

- Deviation from spec §6, decided here: the BPM goes only in `Scan` (seconds per beat), not in `Tags`, because `Tags Bpm` units are not reliably documented and a wrong value would show a wrong BPM in VirtualDJ. The key goes in `Scan`.

- [ ] **Step 1: Write failing tests:**
  - `test_merge_into_empty`.
  - `test_merge_keeps_foreign_songs_and_attributes`: an existing DB with another song and a `Tags Stars="5"` on our song: both survive; our `Scan` and `Poi` entries are replaced, not duplicated.
  - `test_merge_twice_no_duplicates`.
  - `test_xml_escaping`: `&`, `"` and accents in the path and title.
  - `test_unreadable_db_aborts`.
  - `test_running_refuses` (monkeypatch `virtualdj_running`).
  - `test_backup_written`.
  - `test_database_for_other_drive`: `D:\Music\x.mp3` → `D:\VirtualDJ\database.xml`.
- [ ] **Step 2:** The tests fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** The tests pass.
- [ ] **Step 5:** Commit `feat(export): VirtualDJ database merge with backup and lock`.

### Task 7: Serato tags

**Files:**
- Create: `engine/djengine/export/serato.py`
- Test: `engine/tests/export/test_serato.py`

**Interfaces:**
- Consumes: `ExportTrack`, `Cue` (Task 5); `AnalysisStore.restamp`, `StemsStore.restamp`.
- Produces:
  - `encode_autotags(bpm) -> bytes`, `encode_beatgrid(anchor, bpm) -> bytes`, `encode_markers2(cues) -> bytes`.
  - The decoders `decode_beatgrid(b) -> tuple[float, float]` and `decode_markers2(b) -> list[Cue]`.
  - `write_serato(path, track: ExportTrack) -> None`: MP3 through ID3 GEOB, FLAC through Vorbis comments, M4A through freeform atoms. Other formats raise `UserError("unsupported", "Formato no compatible con Serato")`; a locked file raises `UserError("busy", "Archivo en uso")`.
- Byte layouts (from serato-tags, MIT; follow its docs for the container wrapping):
  - **Autotags:** `b"\x01\x01" + f"{bpm:.2f}".encode() + b"\x00" + b"0.000\x00" + b"0.000\x00"`.
  - **BeatGrid:** `b"\x01\x00" + uint32_be(1) + float32_be(anchor) + float32_be(bpm) + b"\x00"`.
  - **Markers2:**
    - Payload: `b"\x01\x01"` + entries + `b"\x00"`, where each entry is `name + b"\x00" + uint32_be(len(data)) + data`.
    - `COLOR`: `b"\x00" + b"\xff\xff\xff"`.
    - `CUE`: `b"\x00" + u8(index) + uint32_be(ms) + b"\x00" + rgb(3) + b"\x00\x00" + utf8(name) + b"\x00"`.
    - `BPMLOCK`: `b"\x00"`.
    - GEOB content: `b"\x01\x01"` + base64 of the payload (no `=` padding, line breaks every 72 characters), zero-padded to at least 470 bytes.
  - **Containers:**
    - MP3: GEOB descriptions `Serato Autotags`, `Serato BeatGrid`, `Serato Markers2`, MIME `application/octet-stream`.
    - FLAC: `SERATO_AUTOTAGS`, `SERATO_BEATGRID`, `SERATO_MARKERS_V2` = base64(`b"application/octet-stream\x00\x00" + b"Serato <Name>\x00" + content`).
    - M4A: `----:com.serato.dj:autotags`, `beatgrid` and `markersv2`, with the same wrapping as FLAC.
  - **Cues:** only the hot cues (first 8). Serato Markers2 has no memory cues.

- [ ] **Step 1: Write failing tests:**
  - `test_beatgrid_bytes`: `encode_beatgrid(0.5, 128.0)` matches the expected bytes, and `decode_beatgrid` gives back (0.5, 128.0).
  - `test_markers2_round_trip`: 3 cues with accents in their names; decoding gives the same index, ms, colour and name.
  - `test_write_mp3_round_trip_keeps_audio_and_other_tags`: real MP3 made with ffmpeg plus a title tag. After writing, the GEOBs decode correctly, the title is unchanged and the MPEG audio frame bytes (`mutagen.mp3` audio start offset, then a hash of everything after it) are unchanged.
  - `test_write_flac_round_trip` and `test_write_m4a_round_trip`.
  - `test_write_twice_replaces`: the same number of GEOB frames after two writes.
  - `test_wav_unsupported`.
  - `test_restamp_after_write`: the analysis is still valid (`get` is not None) after writing.
- [ ] **Step 2:** The tests fail.
- [ ] **Step 3:** Implement. Restamp is done by the caller (Task 8), but `test_restamp_after_write` goes through `export_serato(svc, track)` in this file, so that function does the restamp.
- [ ] **Step 4:** The tests pass.
- [ ] **Step 5:** Commit `feat(export): Serato beatgrid, cues and BPM tags`.

### Task 8: `dj_export` job and endpoint

**Files:**
- Create: `engine/djengine/export/job.py`
- Modify: `engine/djengine/server.py` (`DjExportJobBody` in `JobBody`; concurrency `"dj_export": 1`)
- Test: `engine/tests/export/test_job.py`

**Interfaces:**
- Consumes: `collect`, `rekordbox_xml`, `write_rekordbox` (Task 5); `write_virtualdj` (Task 6); `export_serato` (Task 7); `list_playlists`, `playlist_track_ids` (Task 5).
- Produces:
  - `DjExportJobBody`: `type: Literal["dj_export"]`, `target: Literal["rekordbox","virtualdj","serato"]`, `track_ids: list[int] | None` (None = whole library), `out: str | None` (Rekordbox only; default `<music_dir>/OneForAll rekordbox.xml`).
  - `make_dj_export_runner(svc, target, track_ids, out) -> Runner`, with result `{"exported": int, "skipped": [{title, reason}], "file": str | None}`. Stages `collecting`, then `writing`, with progress per track.

- [ ] **Step 1: Write failing tests:**
  - `test_rekordbox_job_writes_file_with_playlists`.
  - `test_serato_job_skips_wav_and_counts`.
  - `test_virtualdj_job_busy_fails_without_writing`.
  - `test_v1_analysis_exports_grid_without_cues`.
  - `test_unanalysed_skipped`.
  - `test_api_422_on_bad_target`.
- [ ] **Step 2:** The tests fail.
- [ ] **Step 3:** Implement. History action is `"export"`, using the target as the title.
- [ ] **Step 4:** The tests pass, and so does the full engine suite.
- [ ] **Step 5:** Commit `feat(export): dj_export job for Rekordbox, VirtualDJ and Serato`.

### Task 9: UI — client, grid mode in the data sheet

**Files:**
- Modify: `ui/src/lib/types.ts` (`AnalysisSidecar` gains `grid`, `sections`, `needs_reanalysis`; types `Grid` and `Section`), `ui/src/lib/engineClient.ts` (`putGrid(path, op)`, `putSections(path, sections | null)`, `retempo(path, bpm, semis, format?)`, `djExport(target, trackIds | null, out?)`), `ui/src/components/DataSheet.tsx`, `ui/src/components/datasheet.css`
- Create: `ui/src/components/GridControls.tsx`, `ui/src/components/GridControls.test.tsx`

**Interfaces:**
- Consumes: `PUT /analysis/grid` (Task 1).
- Produces:
  - `GridControls({path, grid, position, onChange(grid)})` with these buttons:
    - "El 1 aquí" (anchor = position);
    - "−10 ms" / "+10 ms";
    - "−1 golpe" / "+1 golpe";
    - "÷2" / "×2";
    - "Volver al automático" (reset);
    - "Metrónomo" toggle: clicks follow the grid while the data sheet audio plays, using `Metronome` from `ui/src/mixer/metronome.ts`, with a clock built on the `<audio>` element's `currentTime`.
  - The data sheet gets a "Rejilla" toggle that shows `GridControls`. When `needs_reanalysis` is true it shows "Reanaliza para detectar secciones".

- [ ] **Step 1: Write failing tests:**
  - each button calls `putGrid` with the right operation (`{anchor: 12.5}` when "El 1 aquí" is pressed at position 12.5; `{shift_ms: -10}`; `{shift_beats: 1}`; `{scale: 2}`; `{reset: true}`);
  - the returned grid reaches `onChange`;
  - in DataSheet, `needs_reanalysis` shows the notice;
  - the toggle reveals the controls.
- [ ] **Step 2:** `npx vitest run ui/src/components/GridControls.test.tsx ui/src/components/DataSheet.test.tsx` fails.
- [ ] **Step 3:** Implement. After `onChange`, the waveform `beats` comes from the new sidecar (reload via `getAnalysis`).
- [ ] **Step 4:** The tests pass, and so does the full Vitest suite.
- [ ] **Step 5:** Commit `feat(ui): beat grid editing in the data sheet`.

### Task 10: UI — section bands and editing

**Files:**
- Modify: `ui/src/components/Waveform.tsx` (optional `sections?: Section[]`, drawn as top bands with the label; `onSectionClick?(index)`), `ui/src/components/DataSheet.tsx`
- Create: `ui/src/components/SectionEditor.tsx`, `ui/src/components/SectionEditor.test.tsx`, `ui/src/lib/sections.ts` (labels, colours, pure edit helpers)

**Interfaces:**
- Consumes: `PUT /analysis/sections` (Task 3); `Grid` (Task 9).
- Produces:
  - `sections.ts`: `SECTION_LABELS`, `sectionColor(label)`.
  - Edit helpers:
    - `rename(list, i, label)`;
    - `moveBoundary(list, i, t, snapBars: number[] | null)`, which moves the start of section i (and the end of i−1);
    - `mergeNext(list, i)`;
    - `splitAt(list, t)`;
    - `remove(list, i)`, where the previous section absorbs the removed one.
    All of them return a new valid list.
  - `SectionEditor({path, sections, bars, position, onChange})`: a list of sections. Each row has:
    - a label select;
    - "Inicio al cabezal", which runs `moveBoundary` to the playhead, snapped to the nearest bar, or free with `Alt` held (disabled for the first section);
    - "Unir con la siguiente";
    - "Borrar".
    Below the list: "Partir en el cabezal" and "Volver al automático".

- [ ] **Step 1: Write failing tests:**
  - pure helpers:
    - `moveBoundary` snaps to the nearest bar time and never makes a section shorter than 1 bar;
    - `remove` of the first section extends the next one to start at 0;
    - `splitAt` inside section 2 gives two sections with the same label;
  - the editor calls `putSections` with the edited list, and "Volver al automático" sends `null` (reset);
  - "Inicio al cabezal" at position 33.1 with bars every 1.875 s moves the start to 33.75, and with `altKey` to 33.1;
  - the waveform receives the sections.
- [ ] **Step 2:** The tests fail.
- [ ] **Step 3:** Implement. The bars come from `beats` filtered every 4th from the anchor.
- [ ] **Step 4:** The tests pass.
- [ ] **Step 5:** Commit `feat(ui): sections on the waveform and section editor`.

### Task 11: UI — "Cambiar BPM y tono" sheet

**Files:**
- Create: `ui/src/components/RetempoSheet.tsx`, `ui/src/components/RetempoSheet.test.tsx`
- Modify: `ui/src/stores/uiStore.ts` (`retempoFor: string | null`, `openRetempo(path)`, `closeRetempo()`), `ui/src/App.tsx` (host), `ui/src/components/DataSheet.tsx` (button "Cambiar BPM y tono…"), `ui/src/screens/LibraryScreen.tsx` (action for one selected track)

**Interfaces:**
- Consumes: `client.retempo` (Task 9); `camelotShift` (`ui/src/lib/camelot.ts`).
- Produces: `RetempoSheet({path, onClose})`, which loads the analysis and shows:
  - a BPM slider and number field clamped to [0.5, 1.5] × the source BPM;
  - −/+ semitones with "8A → 10A";
  - a format select (default "Como el original");
  - the name preview, built with the same rule as `retempo_name` (port it to `ui/src/lib/format.ts` as `retempoName`);
  - the "Crear copia" button, which submits the job, shows its progress, and on done shows the new file with "Mostrar en carpeta".

- [ ] **Step 1: Write failing tests:**
  - with source 128 BPM, the slider's min/max are 64 and 192;
  - setting 124 and +2 shows the preview "Song (124 BPM, 10A)";
  - "Crear copia" calls `retempo(path, 124, 2, undefined)`;
  - an unanalysed track shows "Analiza primero" and the button is disabled;
  - `retempoName` gives the same three outputs as `test_retempo_name`.
- [ ] **Step 2:** The tests fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** The tests pass.
- [ ] **Step 5:** Commit `feat(ui): change BPM and key sheet`.

### Task 12: UI — "Exportar a…" in the library

**Files:**
- Create: `ui/src/components/DjExportSheet.tsx`, `ui/src/components/DjExportSheet.test.tsx`
- Modify: `ui/src/screens/LibraryScreen.tsx` (button "Exportar a…"), `ui/src/stores/uiStore.ts` (`djExport: {trackIds: number[] | null} | null` with open/close), `ui/src/App.tsx`

**Interfaces:**
- Consumes: `client.djExport` (Task 9); the jobs store.
- Produces: `DjExportSheet({trackIds, onClose})`:
  - target radio Rekordbox / VirtualDJ / Serato, each with a one-line note:
    - Rekordbox: "Importa el XML en Rekordbox: Preferencias → Avanzado → rekordbox xml";
    - VirtualDJ: "Cierra VirtualDJ antes de exportar";
    - Serato: "Se escribe en las etiquetas de cada archivo (MP3, FLAC, M4A)";
  - scope: "Seleccionadas (n)" or "Toda la biblioteca";
  - for Rekordbox, a destination picker through `window.oneforall.pickFolder`, with the default filename;
  - an "Exportar" button that runs the job and, at the end, shows the summary "<n> exportadas · <m> saltadas" with the list of skipped tracks and their reasons, plus "Mostrar en carpeta" for Rekordbox.

- [ ] **Step 1: Write failing tests:**
  - choosing VirtualDJ with "Toda la biblioteca" calls `djExport('virtualdj', null, undefined)`;
  - the summary shows the counts and the skipped reasons from the job result;
  - a failed job shows its message ("Cierra VirtualDJ para exportar").
- [ ] **Step 2:** The tests fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** The tests pass, and so does the full Vitest suite.
- [ ] **Step 5:** Commit `feat(ui): export to Rekordbox, VirtualDJ and Serato`.

### Task 13: E2E, bench, build, summary

**Files:**
- Modify: `e2e/app.spec.ts`, `README.md` (formats note)
- Create: `docs/bench/2026-11-fase4a-secciones.md` (template for the owner's 10-track check), `docs/diseno/fase4a-resumen.md`

- [ ] **Step 1: Write the E2E test** with the fake engine:
  - download a track, open the data sheet, open Rejilla, press "+1 golpe", and check the grid moved;
  - "Cambiar BPM y tono…" to 0.9× the BPM: the new file appears analysed in the library;
  - "Exportar a…" Rekordbox for the whole library: the XML exists and contains both tracks.
- [ ] **Step 2:** `npm run build && npx playwright test` passes (previous 8 + 1).
- [ ] **Step 3:** Run the full suites: engine pytest and Vitest.
- [ ] **Step 4:** Run sections on 10 reggaeton tracks from `~/Music/OneForAll` (real analysis) and fill in the bench template with the detected boundaries and labels. The owner then marks them by ear. Build with `npm run dist`.
- [ ] **Step 5:** Commit `test(e2e): DJ tools flow; docs: phase 4a summary and sections bench`.
