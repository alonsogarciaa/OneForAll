# OneForAll — Fase 1 Implementation Plan

**Goal:** Build Phase 1 of OneForAll: a Windows desktop app that searches YouTube Music, downloads tracks and playlists, converts formats, tags files, and keeps a library and history, with a Liquid Glass UI.

**Architecture:** An Electron shell (main + preload) spawns a Python FastAPI engine (`djengine`) bound to 127.0.0.1 with a per-session token. The React renderer talks to the engine over HTTP and a WebSocket. Long work runs as cancellable jobs, each in its own temp dir; finished files are moved atomically into the music folder.

**Tech Stack:** Python 3.12 (uv), FastAPI, uvicorn, yt-dlp, ytmusicapi, mutagen, Pillow, psutil, pydantic, pytest + pytest-asyncio + httpx; Node 24, Electron, electron-vite, React 18, TypeScript, zustand, Vitest, Playwright (Electron), electron-builder (NSIS); ffmpeg static build.

**Spec:** `docs/diseno/specs/2026-11-01-dj-app-design.md`

## Global Constraints

- App name: `OneForAll`. App data dir: `%APPDATA%/OneForAll/` containing `library.db`, `settings.json`, `tmp/`, `models/`, `logs/`.
- Default music dir: `<user Music folder>/OneForAll/`. Playlists go to `<music dir>/<playlist name>/`.
- Engine listens only on `127.0.0.1`. Every request must carry header `X-Token`; missing or wrong → 401. The WS takes the token as `?token=`.
- Engine startup prints exactly one stdout line `{"port": N}` when ready.
- Python 3.12 (not 3.14). Electron: `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`.
- Default name template `{artist} - {title}`. Strip `<>:"/\|?*` and control chars. Reserved names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`) get a `_` suffix. Max name length 180 characters. Collisions → `Name (1).ext`, `Name (2).ext` in the same folder; never create a subfolder for a collision.
- Default concurrency: download 3, convert 2.
- Formats: `mp3` (CBR 128/192/256/320, `v0`), `aac` (m4a), `alac` (m4a), `opus`, `ogg`, `flac`, `wav`, `aiff`, `original`. Default `mp3` / `320`. Lossless options: sample rate 44100/48000/96000, bit depth 16/24.
- Cover art: square crop, 600 px, JPEG.
- Log: `logs/engine.log`, rotation 5 × 2 MB.
- UI: tokens from `Liquid_Glass.md` (`--lg-*`), dark mode default, accent `#007AFF`, blur ≤ 20px, at most 2 stacked glass layers, no text under 14px directly on glass, panel radius 16–24px, pill buttons. Fonts Inter + Plus Jakarta Sans 600, bundled (no Google Fonts at runtime). Tinted mode = glass opacity 70%. Window minimum 1024×640, Windows `backgroundMaterial: 'acrylic'`.
- All UI copy is in Spanish. Error copy is fixed by the spec §6.9 (exact strings in Task 7).
- Use the `impeccable` and `ui-ux-pro-max` skills for UI tasks (12–16).

## Review Focus

1. Titles with `/`, `?`, accents or emoji (e.g. `AC/DC - Thunderstruck`, `¿Qué Más Pues?`) → valid filename with illegal characters removed; tags keep the original text. Tested in Task 2 and Task 6.
2. Music folder missing or not writable → missing folder is created; not writable → job fails with code `disk`. Tested in Task 9.
3. Cancel arriving after a job already finished, or during the final move → `cancel` returns `False` and the finished file stays; no half-written file ever appears in the destination. Tested in Task 4 and Task 9.
4. Engine restarts while jobs are running → the UI marks those jobs as failed ("El motor se reinició") instead of showing frozen progress. Tested in Task 11.
5. Playlist containing tracks already in the library → those tracks are skipped without a dialog per track, and the summary reports "N ya en tu biblioteca". Tested in Task 9.

---

## File Structure

```
.gitignore
engine/pyproject.toml
engine/djengine/__init__.py
engine/djengine/__main__.py      CLI: args, port line, uvicorn
engine/djengine/app_paths.py     AppPaths
engine/djengine/settings.py      Settings model, load/save
engine/djengine/logs.py          rotating log setup
engine/djengine/tools.py         locate ffmpeg / yt-dlp
engine/djengine/errors.py        UserError, JobCancelled, ERROR_MESSAGES
engine/djengine/naming.py        filenames, collisions
engine/djengine/library.py       SQLite library + history
engine/djengine/jobs.py          JobManager, JobContext
engine/djengine/convert.py       ffmpeg formats + conversion
engine/djengine/tags.py          mutagen tags + cover
engine/djengine/download.py      yt-dlp download, progress, error mapping
engine/djengine/search.py        ytmusicapi search, fallback, URL resolve
engine/djengine/pipelines.py     download / playlist / convert job runners
engine/djengine/fakes.py         fake search + downloader for --fake mode
engine/djengine/server.py        FastAPI app, routes, WS
engine/tests/...                 one test file per module
app/main/index.ts                window, menu-less, lifecycle, close guard
app/main/engineProcess.ts        spawn, port line, restart policy
app/preload/index.ts             window.oneforall bridge
ui/src/...                       React renderer (see Tasks 12–16)
build/fetch-runtime.ps1          embeddable Python + ffmpeg + yt-dlp into build/runtime
electron-builder.yml
```

---

### Task 1: Repo and engine skeleton (paths, settings, token, startup)

**Files:**
- Create: `.gitignore`, `engine/pyproject.toml`, `engine/djengine/__init__.py`, `engine/djengine/__main__.py`, `engine/djengine/app_paths.py`, `engine/djengine/settings.py`, `engine/djengine/logs.py`, `engine/djengine/server.py`
- Test: `engine/tests/test_server_basics.py`, `engine/tests/conftest.py`

**Interfaces:**
- Produces:
  - `AppPaths` (frozen dataclass): `root, db_path, settings_path, tmp_dir, logs_dir, models_dir: Path`; `AppPaths.from_root(root: Path) -> AppPaths` (creates dirs); `default_root() -> Path` (`%APPDATA%/OneForAll`).
  - `Settings` (pydantic): `music_dir: str`, `default_format: str = "mp3"`, `default_quality: str = "320"`, `name_template: str = "{artist} - {title}"`, `download_concurrency: int = 3` (1–6), `tinted: bool = False`. `load_settings(path: Path) -> Settings` (defaults when the file is missing or corrupt), `save_settings(path: Path, s: Settings) -> None`. `music_dir` defaults to `~/Music/OneForAll`.
  - `setup_logging(logs_dir: Path) -> None` (RotatingFileHandler, 2 MB × 5).
  - `Services` (dataclass in `server.py`): `paths, settings, library, jobs, search, downloader, fake: bool`. Fields not built yet may be `None` until their task.
  - `create_app(services: Services, token: str) -> FastAPI`, with routes `GET /health` → `{"ok": true}`, `GET /settings`, `PUT /settings`.
  - CLI: `python -m djengine --port 0 --token T [--data-root DIR] [--fake]`.

- [ ] **Step 1: Init repo and env**
  `git init`; `.gitignore` covers `node_modules/`, `out/`, `dist/`, `engine/.venv/`, `__pycache__/`, `build/runtime/`, `*.log`. In `engine/`: `uv init --package --python 3.12` adjusted to the `djengine` name (install uv with `py -m pip install uv` if missing); add deps `fastapi uvicorn[standard] pydantic yt-dlp ytmusicapi mutagen pillow psutil` and dev deps `pytest pytest-asyncio httpx`. Set `asyncio_mode = "auto"`.
  Run: `cd engine; uv run python -c "import fastapi, yt_dlp, ytmusicapi, mutagen, PIL, psutil"`. Expected: no output, exit 0.

- [ ] **Step 2: Write failing tests** in `test_server_basics.py`. `conftest.py` provides fixture `paths(tmp_path)` → `AppPaths.from_root(tmp_path)` and `client` → `TestClient(create_app(Services(paths, load_settings(...), None, None, None, None, False), token="t"))`.
```python
def test_health_requires_token(client):
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"X-Token": "bad"}).status_code == 401
    assert client.get("/health", headers={"X-Token": "t"}).json() == {"ok": True}

def test_settings_roundtrip_persists(client, paths):
    h = {"X-Token": "t"}
    s = client.get("/settings", headers=h).json()
    assert s["default_format"] == "mp3" and s["name_template"] == "{artist} - {title}"
    s["default_format"] = "flac"
    assert client.put("/settings", json=s, headers=h).status_code == 200
    assert load_settings(paths.settings_path).default_format == "flac"

def test_corrupt_settings_fall_back_to_defaults(paths):
    paths.settings_path.write_text("{not json")
    assert load_settings(paths.settings_path).download_concurrency == 3

def test_cli_prints_port_line(tmp_path):
    # start `python -m djengine --port 0 --token t --data-root tmp_path` as subprocess,
    # read first stdout line within 15 s, kill process
    assert re.fullmatch(r'\{"port": \d+\}', first_line)
```

- [ ] **Step 3: Run** `cd engine; uv run pytest tests/test_server_basics.py -v`. Expected: FAIL (import errors).

- [ ] **Step 4: Implement** the files above. Token check runs as a dependency on every route; the WS path checks the `token` query param instead. `__main__` binds a socket on `127.0.0.1:0` to learn the port, prints the line with `flush=True`, then runs uvicorn on that socket (`uvicorn.Server(config).run(sockets=[sock])`).

- [ ] **Step 5: Run** the same command. Expected: 4 passed.

- [ ] **Step 6: Commit** `git add -A; git commit -m "feat(engine): skeleton with token auth, settings and startup port line"`

---

### Task 2: File naming and collisions

**Files:** Create `engine/djengine/naming.py`. Test `engine/tests/test_naming.py`.

**Interfaces:**
- Produces: `sanitize_filename(name: str) -> str`; `render_name(template: str, meta: dict[str, str]) -> str` (missing keys → `""`, then collapses doubled separators like `" - "` at the edges; empty result → `"Sin título"`); `unique_path(directory: Path, stem: str, ext: str) -> Path` (ext without dot; never creates directories).

- [ ] **Step 1: Write failing tests**
```python
def test_strips_illegal_chars():
    assert sanitize_filename('AC/DC - Thunder:struck?') == "ACDC - Thunderstruck"
def test_keeps_accents_and_emoji():
    assert sanitize_filename("¿Qué Más Pues? 🔥") == "¿Qué Más Pues 🔥"
def test_reserved_names():
    assert sanitize_filename("CON") == "CON_"
def test_trailing_dots_spaces_removed_and_length_capped():
    assert sanitize_filename("a. ") == "a"
    assert len(sanitize_filename("x" * 400)) == 180
def test_render_missing_artist():
    assert render_name("{artist} - {title}", {"title": "Song"}) == "Song"
def test_collision_same_folder(tmp_path):
    (tmp_path / "A - B.mp3").touch()
    p1 = unique_path(tmp_path, "A - B", "mp3"); assert p1 == tmp_path / "A - B (1).mp3"
    p1.touch()
    assert unique_path(tmp_path, "A - B", "mp3") == tmp_path / "A - B (2).mp3"
    assert [d for d in tmp_path.iterdir() if d.is_dir()] == []
```
- [ ] **Step 2: Run** `uv run pytest tests/test_naming.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** in `naming.py`.
- [ ] **Step 4: Run** the same command. Expected: 6 passed.
- [ ] **Step 5: Commit** `feat(engine): filename sanitizing and same-folder collision suffixes`

---

### Task 3: Library and history (SQLite)

**Files:** Create `engine/djengine/library.py`. Test `engine/tests/test_library.py`.

**Interfaces:**
- Produces:
  - `TrackRecord` dataclass: `id: int | None, video_id: str | None, title, artist, album: str, duration_s: int | None, views: int | None, path: str, format: str, bitrate: int | None, cover_path: str | None, added_at: str, bpm: float | None = None, musical_key: str | None = None, camelot: str | None = None, missing: bool = False`.
  - `HistoryEntry` dataclass: `id, track_id, video_id, title, artist, action, status, at`.
  - `normalize_key(artist: str, title: str) -> str`: lowercase, strip accents, remove bracketed parts containing `official|video|audio|lyrics|letra|visualizer|hd|4k`, remove `ft.|feat.|featuring …` to the end, collapse non-alphanumerics to single spaces.
  - `class Library(db_path: Path)`: `add_track(rec) -> int`; `find_duplicate(video_id: str | None, artist: str, title: str) -> TrackRecord | None`; `list_tracks(q: str = "") -> list[TrackRecord]` (newest first, LIKE over title/artist/album); `refresh_missing() -> int` (sets `missing` when the path doesn't exist; returns the count); `add_history(video_id, title, artist, action, status, track_id=None) -> int`; `list_history() -> list[HistoryEntry]`; `delete_history(ids: list[int] | None) -> int` (`None` = all); `add_playlist(yt_id, name, path) -> int`; `add_playlist_track(playlist_id, track_id, position) -> None`.
  - Schema exactly as spec §6.5 plus `tracks.norm_key TEXT` (indexed) and `tracks.missing INTEGER DEFAULT 0`. Thread-safe: one connection per call, or a lock with `check_same_thread=False`.

- [ ] **Step 1: Write failing tests**
```python
def test_normalize_key_strips_noise():
    assert normalize_key("Quevedo", "La Graciosa (Official Video)") == normalize_key("quevedo", "la graciosa")
    assert normalize_key("Bad Bunny", "Song ft. Drake") == normalize_key("Bad Bunny", "Song")
    assert normalize_key("Rosalía", "Despechá") == normalize_key("Rosalia", "Despecha")
def test_duplicate_by_video_id_and_by_name(lib):
    lib.add_track(rec(video_id="abc", artist="Quevedo", title="La Graciosa"))
    assert lib.find_duplicate("abc", "", "") is not None
    assert lib.find_duplicate("zzz", "QUEVEDO", "La Graciosa (Lyrics)") is not None
    assert lib.find_duplicate("zzz", "Other", "Song") is None
def test_history_delete_selected_and_all(lib):
    ids = [lib.add_history("v%d" % i, "t", "a", "download", "done") for i in range(3)]
    assert lib.delete_history([ids[0]]) == 1 and len(lib.list_history()) == 2
    assert lib.delete_history(None) == 2 and lib.list_history() == []
def test_refresh_missing_marks_not_deletes(lib, tmp_path):
    lib.add_track(rec(path=str(tmp_path / "gone.mp3")))
    assert lib.refresh_missing() == 1
    assert lib.list_tracks()[0].missing is True
def test_bpm_key_columns_exist(lib):
    assert lib.list_tracks() == [] and {"bpm", "musical_key", "camelot"} <= columns(lib, "tracks")
```
- [ ] **Step 2: Run** `uv run pytest tests/test_library.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `library.py`.
- [ ] **Step 4: Run** the same command. Expected: 5 passed.
- [ ] **Step 5: Commit** `feat(engine): sqlite library, duplicate detection and history`

---

### Task 4: Job manager (queues, temp dirs, cancellation)

**Files:** Create `engine/djengine/errors.py`, `engine/djengine/jobs.py`. Test `engine/tests/test_jobs.py`.

**Interfaces:**
- Produces:
  - `errors.py`: `class UserError(Exception)` with `code: str, message: str`; `class JobCancelled(Exception)`.
  - `Job` dataclass: `id: str (uuid4 hex), type: str, status: Literal["queued","running","done","failed","cancelled"], stage: str, pct: float, parent_id: str | None, title: str, error: dict | None ({"code","message"}), result: dict | None, children: list[str]`. `Job.to_dict() -> dict`.
  - `JobContext`: `job: Job`, `tmp_dir: Path` (created as `tmp_root/<job.id>`), `report(stage: str, pct: float, speed: str | None = None, eta: str | None = None) -> None`, `register_process(proc: asyncio.subprocess.Process) -> None`, `check_cancelled() -> None` (raises `JobCancelled`).
  - `Runner = Callable[[JobContext], Awaitable[dict | None]]`.
  - `JobManager(tmp_root: Path, emit: Callable[[dict], Awaitable[None]], concurrency: dict[str, int])`: `submit(type: str, title: str, runner: Runner, parent_id: str | None = None) -> Job`; `async cancel(job_id: str) -> bool` (`False` when unknown or finished; cancels children too); `list() -> list[Job]`; `get(id) -> Job | None`; `active_count() -> int` (queued + running, excluding parents); `purge_orphans() -> int` (removes everything in `tmp_root`; call it at startup); `set_concurrency(type, n)`. Type `"playlist"` has no concurrency limit (it is a parent).
  - Events emitted: `{"type": "job.progress", "job": job.to_dict(), "speed": ..., "eta": ...}`, `job.done`, `job.failed`, `job.cancelled`, `job.queued`. Progress events are throttled to at most 1 per 200 ms per job.
  - Behavior: on any exit (done, failed or cancelled) `tmp_dir` is deleted. `UserError` → failed with its code. Any other exception → failed with `{"code": "internal", "message": "Error inesperado"}`, logged with traceback. Cancel = set flag, kill the process tree of each registered process (`psutil.Process(pid).children(recursive=True)` + self), cancel the asyncio task, emit `job.cancelled`.

- [ ] **Step 1: Write failing tests** (pytest-asyncio; `emit` collects into a list)
```python
async def test_runs_and_cleans_tmp(mgr, tmp_root):
    async def r(ctx): (ctx.tmp_dir / "x").write_text("1"); ctx.report("downloading", 50); return {"ok": 1}
    job = mgr.submit("download", "t", r); await wait_done(mgr, job.id)
    assert mgr.get(job.id).status == "done" and not (tmp_root / job.id).exists()
async def test_cancel_kills_process_and_cleans(mgr, tmp_root):
    async def r(ctx):
        p = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(60)")
        ctx.register_process(p); (ctx.tmp_dir / "partial").write_text("x"); await p.wait()
    job = mgr.submit("download", "t", r); await asyncio.sleep(0.5)
    assert await mgr.cancel(job.id) is True
    await wait_done(mgr, job.id)
    assert mgr.get(job.id).status == "cancelled" and not (tmp_root / job.id).exists()
    assert not psutil.pid_exists(pid_of_child)  # captured via the register hook
async def test_cancel_one_does_not_touch_others(mgr): ...  # two jobs, cancel A, B ends "done"
async def test_cancel_after_done_returns_false(mgr): ...
async def test_concurrency_limit(mgr): ...  # convert limit 2: third job stays "queued" while 2 run
async def test_user_error_maps_code(mgr): ...  # runner raises UserError("offline","Sin conexión") -> error.code == "offline"
async def test_parent_cancel_cancels_children(mgr): ...
def test_purge_orphans(tmp_root): ...  # stale dir removed
```
- [ ] **Step 2: Run** `uv run pytest tests/test_jobs.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `errors.py`, `jobs.py`. Use one `asyncio.Semaphore` per type.
- [ ] **Step 4: Run** the same command. Expected: 8 passed.
- [ ] **Step 5: Commit** `feat(engine): job manager with per-job cancel and temp cleanup`

---

### Task 5: Format conversion (ffmpeg)

**Files:** Create `engine/djengine/tools.py`, `engine/djengine/convert.py`. Test `engine/tests/test_convert.py`.

**Interfaces:**
- Consumes: `JobContext` (Task 4).
- Produces:
  - `find_tool(name: Literal["ffmpeg","ffprobe","yt-dlp"]) -> str`: checks the `ONEFORALL_TOOLS` env dir first, then PATH; raises `UserError("internal", "Falta <name>")`.
  - `FormatSpec` dataclass: `ext: str, lossless: bool`. `FORMATS: dict[str, FormatSpec]` = mp3→mp3, aac→m4a, alac→m4a (lossless), opus→opus, ogg→ogg, flac→flac (lossless), wav→wav (lossless), aiff→aiff (lossless), original→(the source ext).
  - `ConvertOptions` (pydantic): `format: str`, `quality: str | None = None`, `sample_rate: int | None = None`, `bit_depth: int | None = None`. Validate quality against `{"128","192","256","320","v0"}` for mp3; sample rate and bit depth only accepted for lossless formats.
  - `build_ffmpeg_args(src: Path, dst: Path, opts: ConvertOptions) -> list[str]`. Codecs: mp3 `libmp3lame -b:a <q>k` or `-q:a 0` for v0; aac `aac -b:a 256k`; alac `alac`; opus `libopus -b:a 160k`; ogg `libvorbis -q:a 6`; flac `flac`; wav `pcm_s16le`/`pcm_s24le`; aiff `pcm_s16be`/`pcm_s24be`. Always `-vn -map_metadata 0 -y -progress pipe:1 -nostats`.
  - `async convert_file(ctx: JobContext, src: Path, dst: Path, opts: ConvertOptions, duration_s: float | None) -> Path`: runs ffmpeg, registers the process, reports `("converting", pct)` from `out_time_ms`. A non-zero exit raises `UserError("internal", "No se pudo convertir el archivo")`.

- [ ] **Step 1: Write failing tests.** A fixture generates a 3 s sine WAV with `ffmpeg -f lavfi -i sine=f=440:d=3`. Skip the module if ffmpeg is missing (CI runs Task 1 setup with ffmpeg on PATH; locally run `winget install Gyan.FFmpeg`).
```python
@pytest.mark.parametrize("fmt", ["mp3","aac","alac","opus","ogg","flac","wav","aiff"])
async def test_convert_each_format(ctx, sine_wav, tmp_path, fmt):
    dst = tmp_path / f"out.{FORMATS[fmt].ext}"
    await convert_file(ctx, sine_wav, dst, ConvertOptions(format=fmt), 3.0)
    assert mutagen.File(dst) is not None and abs(mutagen.File(dst).info.length - 3.0) < 0.2
def test_mp3_quality_args():
    a = build_ffmpeg_args(Path("i.wav"), Path("o.mp3"), ConvertOptions(format="mp3", quality="320"))
    assert a[a.index("-b:a") + 1] == "320k"
def test_24bit_wav():
    a = build_ffmpeg_args(Path("i"), Path("o.wav"), ConvertOptions(format="wav", bit_depth=24, sample_rate=96000))
    assert "pcm_s24le" in a and "96000" in a
def test_rejects_sample_rate_on_lossy():
    with pytest.raises(ValidationError): ConvertOptions(format="mp3", sample_rate=96000)
```
- [ ] **Step 2: Run** `uv run pytest tests/test_convert.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `tools.py`, `convert.py`.
- [ ] **Step 4: Run** the same command. Expected: 11 passed.
- [ ] **Step 5: Commit** `feat(engine): ffmpeg conversion to all formats`

---

### Task 6: Tags and cover art

**Files:** Create `engine/djengine/tags.py`. Test `engine/tests/test_tags.py`.

**Interfaces:**
- Produces: `TrackMeta` dataclass: `title, artist: str, album: str = "", year: str = "", source_url: str = "", bpm: float | None = None, key: str | None = None`. `square_cover(img: bytes, size: int = 600) -> bytes` (center crop, JPEG q90). `write_tags(path: Path, meta: TrackMeta, cover: bytes | None) -> None` for mp3 (ID3v2.4 TIT2/TPE1/TALB/TDRC/COMM/APIC, plus TBPM/TKEY when set), m4a (`©nam ©ART ©alb ©day ©cmt covr`, plus `tmpo`), flac/ogg/opus (Vorbis comments + METADATA_BLOCK_PICTURE, plus `BPM`/`INITIALKEY`), wav/aiff (ID3 chunk). `read_tags(path: Path) -> TrackMeta`.

- [ ] **Step 1: Write failing tests.** Use the Task 5 sine fixture converted to each format.
```python
@pytest.mark.parametrize("fmt", ["mp3","aac","flac","ogg","opus","wav","aiff"])
def test_roundtrip(fmt, audio_file_factory):
    p = audio_file_factory(fmt)
    write_tags(p, TrackMeta("¿Qué Más Pues?", "J Balvin", "Álbum", "2016", "https://youtu.be/x", bpm=96.0, key="8A"), red_png_bytes())
    m = read_tags(p)
    assert (m.title, m.artist, m.album) == ("¿Qué Más Pues?", "J Balvin", "Álbum")
    assert m.bpm == 96.0 and m.key == "8A"
def test_square_cover():
    out = Image.open(io.BytesIO(square_cover(png_bytes(1280, 720))))
    assert out.size == (600, 600) and out.format == "JPEG"
```
- [ ] **Step 2: Run** `uv run pytest tests/test_tags.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `tags.py`. For m4a, `key` goes in the freeform atom `----:com.apple.iTunes:initialkey`.
- [ ] **Step 4: Run** the same command. Expected: 8 passed.
- [ ] **Step 5: Commit** `feat(engine): tag writing with cover for all formats`

---

### Task 7: yt-dlp download, progress and error mapping

**Files:** Create `engine/djengine/download.py`; add the `ERROR_MESSAGES` dict to `errors.py`. Test `engine/tests/test_download.py`, `engine/tests/fixtures/fake_ytdlp.py`.

**Interfaces:**
- Consumes: `JobContext`, `find_tool`, `UserError`.
- Produces:
  - `ERROR_MESSAGES: dict[str, str]` exactly: `unavailable` → `"Este vídeo ya no está disponible"`, `blocked` → `"YouTube bloquea este vídeo (edad/región)"`, `offline` → `"Sin conexión"`, `extractor_outdated` → `"YouTube ha cambiado; actualiza yt-dlp"`, `disk` → `"No se puede escribir en la carpeta de destino"`.
  - `map_ytdlp_error(stderr: str) -> UserError`. Patterns (case-insensitive): `Private video|Video unavailable|has been removed|This video is not available` → unavailable; `Sign in to confirm your age|age-restricted|not available in your country|geo` → blocked; `getaddrinfo|Network is unreachable|timed out|Temporary failure in name resolution|Failed to resolve` → offline; `No space left|Permission denied|Errno 28|Errno 13` → disk; `Unable to extract|Signature extraction failed|nsig|HTTP Error 403` and anything else → extractor_outdated.
  - `parse_progress(line: str) -> tuple[float, str | None, str | None] | None`, parsing lines like `[download]  42.3% of ~4.20MiB at 1.21MiB/s ETA 00:03`.
  - `async download_audio(ctx: JobContext, url: str) -> Path`: runs `yt-dlp -f bestaudio --no-playlist --newline --no-part -o "<tmp>/src.%(ext)s" <url>`, reports `("downloading", pct, speed, eta)`, returns the single `src.*` file. Non-zero exit → `map_ytdlp_error(stderr)`.
  - `fetch_thumbnail(url: str) -> bytes | None` (urllib, 10 s timeout, `None` on failure).
  - `YTDLP_CMD` resolution: `find_tool("yt-dlp")`. If the env var `ONEFORALL_YTDLP` is set, use it as the full command (tests point it to `python fake_ytdlp.py`).

- [ ] **Step 1: Write failing tests**
```python
def test_parse_progress():
    assert parse_progress("[download]  42.3% of ~4.20MiB at 1.21MiB/s ETA 00:03") == (42.3, "1.21MiB/s", "00:03")
    assert parse_progress("[info] something") is None
@pytest.mark.parametrize("stderr,code", [
    ("ERROR: [youtube] x: Private video", "unavailable"),
    ("ERROR: Sign in to confirm your age", "blocked"),
    ("urlopen error [Errno 11001] getaddrinfo failed", "offline"),
    ("OSError: [Errno 28] No space left on device", "disk"),
    ("ERROR: Unable to extract nsig function", "extractor_outdated"),
])
def test_error_mapping(stderr, code):
    e = map_ytdlp_error(stderr); assert e.code == code and e.message == ERROR_MESSAGES[code]
async def test_download_with_fake_ytdlp(ctx, monkeypatch):
    monkeypatch.setenv("ONEFORALL_YTDLP", f'"{sys.executable}" "{FAKE}"')
    p = await download_audio(ctx, "https://youtu.be/ok")
    assert p.name.startswith("src.") and p.parent == ctx.tmp_dir and reported_pcts(ctx)[-1] == 100.0
async def test_download_failure_maps(ctx, monkeypatch): ...  # fake exits 1 printing "Private video" -> UserError unavailable
```
  `fake_ytdlp.py`: prints 3 progress lines, writes `src.webm` (copy of the sine fixture) to the `-o` path, exits 0. URL containing `private` → prints the error to stderr and exits 1.
- [ ] **Step 2: Run** `uv run pytest tests/test_download.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command. Expected: 8 passed.
- [ ] **Step 5: Commit** `feat(engine): yt-dlp download with progress and friendly errors`

---

### Task 8: Search (YouTube Music + fallback + URL resolve)

**Files:** Create `engine/djengine/search.py`. Test `engine/tests/test_search.py`, `engine/tests/fixtures/ytm_songs.json`, `ytm_videos.json`, `ytm_playlists.json`, `ytm_playlist.json` (captured once with ytmusicapi, trimmed to 5 items each, including one broken item without duration and one without title).

**Interfaces:**
- Produces:
  - `SearchResult` (pydantic): `kind: Literal["song","video","playlist"], id: str, title: str, artist: str, album: str = "", duration_s: int | None, views: int | None, thumbnail: str | None, url: str, track_count: int | None = None, in_library: bool = False`.
  - `PlaylistInfo` (pydantic): `id, title: str, tracks: list[SearchResult]`.
  - `parse_views(text: str | None) -> int | None` (`"1.2M"` → 1200000, `"350K views"` → 350000, `"12,345"` → 12345).
  - `filter_results(items: list[SearchResult]) -> list[SearchResult]`: drops items with empty title or empty id; for song/video kinds also drops items with `duration_s` None. Song kind keeps 60–1200 s; video kind keeps any duration ≥ 60 s (sets and mixes allowed).
  - `resolve_url(text: str) -> tuple[Literal["song","playlist"], str] | None`, for `youtube.com/watch?v=`, `youtu.be/`, `music.youtube.com/watch?v=`, `list=` (playlist wins when there is no `v`; when both are present → song), `/shorts/` → song.
  - `class SearchService(ytm: YTMusic | None = None, fallback: Callable[[str], list[dict]] | None = None)`: `search(q: str, kind: Literal["songs","videos","playlists"]) -> list[SearchResult]` (max 30; when `resolve_url(q)` matches, returns that single item via `get_song` or `get_playlist`); `get_playlist(id: str) -> PlaylistInfo` (limit 500). If ytmusicapi raises, use the fallback (`yt_dlp.YoutubeDL({"extract_flat": True, "quiet": True}).extract_info("ytsearch30:" + q)`) mapped to `kind="video"` and filtered.

- [ ] **Step 1: Write failing tests** with a stub YTMusic returning the fixtures.
```python
def test_songs_mapped_and_broken_dropped(svc):
    r = svc.search("la graciosa quevedo", "songs")
    assert r[0].kind == "song" and r[0].artist and r[0].duration_s
    assert all(x.title and x.duration_s for x in r)
def test_parse_views():
    assert parse_views("1.2M") == 1_200_000 and parse_views("350K views") == 350_000 and parse_views(None) is None
@pytest.mark.parametrize("u,exp", [
    ("https://youtu.be/abc123", ("song","abc123")),
    ("https://music.youtube.com/watch?v=abc123&list=PLx", ("song","abc123")),
    ("https://www.youtube.com/playlist?list=PLx", ("playlist","PLx")),
    ("la graciosa", None)])
def test_resolve_url(u, exp): assert resolve_url(u) == exp
def test_fallback_on_ytm_error():
    svc = SearchService(ytm=Exploding(), fallback=lambda q: [fake_flat_entry(duration=200), fake_flat_entry(duration=None)])
    assert len(svc.search("x", "songs")) == 1
def test_playlist(svc): assert len(svc.get_playlist("PLx").tracks) >= 1
```
- [ ] **Step 2: Run** `uv run pytest tests/test_search.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command. Expected: 9 passed.
- [ ] **Step 5: Add an online smoke test** `test_search_online` marked `@pytest.mark.online` (skipped by default via `addopts = "-m 'not online'"`): real search `"la graciosa quevedo"` songs → some result in the top 3 has `"graciosa"` in the title.
- [ ] **Step 6: Commit** `feat(engine): youtube music search with fallback and url resolve`

---

### Task 9: Pipelines and full API (jobs, library, history, WS, fake mode)

**Files:** Create `engine/djengine/pipelines.py`, `engine/djengine/fakes.py`; modify `engine/djengine/server.py`, `engine/djengine/__main__.py`. Test `engine/tests/test_pipelines.py`, `engine/tests/test_api.py`.

**Interfaces:**
- Consumes: everything from Tasks 1–8.
- Produces:
  - `DownloadRequest` (pydantic): `target: SearchResult`, `options: ConvertOptions`, `force: bool = False`, `skip_existing: bool = False`.
  - `pipelines.make_download_runner(svc: Services, req: DownloadRequest, dest_dir: Path, playlist_id: int | None = None, position: int | None = None) -> Runner`. Stages: `downloading` → `converting` (skipped for `original`) → `tagging` → `finalizing`. Finalizing: `mkdir(parents=True, exist_ok=True)` on `dest_dir` (an `OSError` → `UserError("disk", …)`), `unique_path` with `render_name(settings.name_template, …)`, `os.replace` from tmp, `library.add_track`, `library.add_history(..., "download", "done")`, optionally `add_playlist_track`. `check_cancelled()` runs right before `os.replace`; after `os.replace` the job is not cancellable (it is marked as finishing). Returns `{"path": str, "track_id": int}`. When `skip_existing` is set and `find_duplicate` hits → returns `{"skipped": True, "existing_path": ...}` without downloading.
  - `pipelines.start_playlist(svc, playlist_id: str, options: ConvertOptions) -> Job`: fetches `PlaylistInfo`, creates the parent job type `"playlist"` and folder `music_dir/sanitize(title)`, submits one child per track with `skip_existing=True`. The parent finishes when every child finishes; its `result` = `{"done": n, "failed": [{"title","code","message","child_id"}], "skipped": n}`.
  - `pipelines.make_convert_runner(svc, src: Path, options: ConvertOptions) -> Runner`: output goes next to the source with `unique_path(src.parent, src.stem, ext)`; the original is never modified; adds a history entry with action `"convert"`.
  - `fakes.FakeSearch` (returns 3 fixed songs, a fixed video and a fixed playlist of 3 tracks, one of them "private") and `fakes.fake_downloader` (copies a bundled 5 s tone in 2 s with progress; title containing "Private" → `UserError("unavailable")`). `--fake` swaps them into `Services` (`downloader` field = callable with the signature of `download_audio`).
  - Routes, per spec §4:
    - `GET /search?q&kind` → list; each item gets `in_library` from `find_duplicate`.
    - `GET /playlist/{id}`.
    - `POST /jobs` body `{"type":"download", "request": DownloadRequest}` → 409 `{"duplicate": TrackRecord}` when a duplicate exists and `force` is false; playlists `{"type":"playlist","id":..., "options":...}`; `{"type":"convert","paths":[...],"options":...}` → list of jobs.
    - `GET /jobs`, `DELETE /jobs/{id}` → `{"cancelled": bool}`, `GET /jobs/active-count` → `{"count": n, "by_type": {...}}`.
    - `GET /library?q`, `GET /library/duplicate?videoId&artist&title` → `{"duplicate": TrackRecord | null}`, `GET /history`, `DELETE /history` body `{"ids": [...]}` or `{"all": true}`.
    - `POST /tools/ytdlp/update` → runs `yt-dlp -U` and returns `{"ok": bool, "output": str}`.
    - `POST /shutdown` → cancels all jobs, then exits.
    - `WS /events?token=` → broadcasts the JobManager events plus `{"type":"engine.hello"}` on connect.
  - Startup: `purge_orphans()`, `library.refresh_missing()`, logging setup, `JobManager.set_concurrency("download", settings.download_concurrency)`. `PUT /settings` re-applies the concurrency.

- [ ] **Step 1: Write failing pipeline tests** (fake downloader, real ffmpeg, tmp music dir)
```python
async def test_download_end_to_end(svc, music_dir):
    job = submit_download(svc, song("Quevedo", "La Graciosa"), "mp3")
    await wait_done(svc.jobs, job.id)
    f = music_dir / "Quevedo - La Graciosa.mp3"
    assert f.exists() and read_tags(f).title == "La Graciosa"
    assert svc.library.find_duplicate(None, "Quevedo", "La Graciosa") and svc.library.list_history()[0].status == "done"
async def test_force_duplicate_goes_to_suffix_same_folder(svc, music_dir): ...  # second download, force=True -> "Quevedo - La Graciosa (1).mp3", no subdirs
async def test_missing_music_dir_is_created(svc, tmp_path): ...
async def test_unwritable_dest_fails_with_disk(svc, monkeypatch): ...  # os.replace raises PermissionError -> error.code == "disk"
async def test_cancel_mid_download_leaves_nothing(svc, music_dir): ...  # dest empty, tmp empty
async def test_playlist_continues_on_failure_and_skips_existing(svc, music_dir):
    pre_add_existing(svc, track_2)
    job = start_playlist(svc, "PLfake", ConvertOptions(format="mp3"))
    await wait_done(svc.jobs, job.id)
    r = svc.jobs.get(job.id).result
    assert r["done"] == 1 and r["skipped"] == 1 and r["failed"][0]["code"] == "unavailable"
    assert (music_dir / "Fake Playlist").is_dir()
async def test_convert_keeps_original(svc, tmp_path): ...
```
- [ ] **Step 2: Write failing API tests** (TestClient, `--fake` services): 401 without token on `/jobs`; `POST /jobs` duplicate → 409 with a `duplicate` body; `DELETE /history` with `ids` and with `all`; `GET /jobs/active-count` while a job runs → `count == 1`; WS receives `engine.hello` and then `job.done` for a fake download.
- [ ] **Step 3: Run** `uv run pytest tests/test_pipelines.py tests/test_api.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** `pipelines.py`, `fakes.py`, the routes and the startup wiring.
- [ ] **Step 5: Run** `uv run pytest -v`. Expected: all tests pass, online tests deselected.
- [ ] **Step 6: Commit** `feat(engine): download/playlist/convert pipelines and full REST+WS api`

---

### Task 10: Electron shell (window, engine process, preload, close guard)

**Files:** Create `package.json` (root; scripts `dev`, `build`, `test`, `e2e`, `dist`), `electron.vite.config.ts`, `tsconfig*.json`, `app/main/index.ts`, `app/main/engineProcess.ts`, `app/preload/index.ts`, `ui/index.html`, `ui/src/main.tsx` (placeholder). Test `app/main/engineProcess.test.ts`.

**Interfaces:**
- Produces:
  - `parsePortLine(line: string): number | null`.
  - `class RestartPolicy(maxPerMinute = 3)`: `shouldRestart(now: number): boolean`.
  - `class EngineProcess(opts: { pythonCmd: string[]; dataRoot: string; fake: boolean; toolsDir?: string })`: `start(): Promise<{ baseUrl: string; token: string }>`, emits `'ready' | 'restarting' | 'failed'`, `stop(): Promise<void>` (`POST /shutdown`, then kill after 3 s). Dev python command: `engine/.venv/Scripts/python.exe -m djengine`; packaged: `resources/runtime/python/python.exe -m djengine`. Env `ONEFORALL_TOOLS` = `resources/runtime/bin` when packaged. `--fake` when env `ONEFORALL_FAKE=1`.
  - Preload `window.oneforall`: `getEngine(): Promise<{ baseUrl: string; token: string }>`, `onEngineState(cb: (s: 'ready' | 'restarting' | 'failed') => void): () => void`, `pathForFile(f: File): string` (`webUtils.getPathForFile`), `pickFolder(): Promise<string | null>`, `showInFolder(path: string): void`, `openPath(path: string): void`, `setTitleBarTheme(dark: boolean): void`. Types in `ui/src/types/oneforall.d.ts`.
  - Window: `width 1280, height 800, minWidth 1024, minHeight 640, backgroundMaterial: 'acrylic', backgroundColor: '#00000000', titleBarStyle: 'hidden', titleBarOverlay: { color: '#00000000', symbolColor: '#ffffff', height: 44 }`, macOS `vibrancy: 'under-window'`. CSP: `default-src 'self'; connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'`.
  - Close guard: on `close`, call `GET /jobs/active-count`; when count > 0, show a native dialog with the message `Hay N procesos en curso (descargas/conversiones). ¿Cerrar y cancelarlos?` and buttons `Cancelar` / `Cerrar y cancelar`; on confirm call `stop()` and then quit.

- [ ] **Step 1: Scaffold** with electron-vite (`main` → `app/main`, `preload` → `app/preload`, `renderer` root → `ui`). Install `electron electron-vite vite react react-dom typescript zustand vitest @vitejs/plugin-react`.
- [ ] **Step 2: Write failing tests**: `parsePortLine('{"port": 51234}') === 51234`; `parsePortLine('INFO started') === null`; RestartPolicy allows 3 restarts within 60 s, refuses the 4th, and allows again after 60 s.
- [ ] **Step 3: Run** `npx vitest run app` . Expected: FAIL.
- [ ] **Step 4: Implement** the main, preload and engine process. When the engine fails 4 times in a minute, emit `'failed'` (the UI shows the error with a "Reintentar" button that calls a new preload method `restartEngine()`).
- [ ] **Step 5: Run** `npx vitest run app`, then `npm run dev`. Expected: tests pass; the window opens with acrylic and the placeholder shows the result of `/health` (temporary text `Motor OK`).
- [ ] **Step 6: Commit** `feat(app): electron shell with acrylic window, engine process and close guard`

---

### Task 11: UI foundation (tokens, shell layout, engine client, stores)

**Files:** Create `ui/src/styles/tokens.css`, `ui/src/styles/glass.css`, `ui/src/lib/engineClient.ts`, `ui/src/lib/types.ts`, `ui/src/stores/jobsStore.ts`, `ui/src/stores/uiStore.ts`, `ui/src/components/AppShell.tsx`, `Sidebar.tsx`, `TopBar.tsx`, `MiniQueue.tsx`, `GlassSheet.tsx`, `Toasts.tsx`, `ui/src/App.tsx`. Test `ui/src/lib/engineClient.test.ts`, `ui/src/stores/jobsStore.test.ts`.

**Interfaces:**
- Consumes: the preload API (Task 10) and the engine routes and event shapes (Task 9).
- Produces:
  - `types.ts`: TS mirrors of `SearchResult`, `PlaylistInfo`, `TrackRecord`, `HistoryEntry`, `Job`, `ConvertOptions`, `Settings`, `EngineEvent`.
  - `createClient({ baseUrl, token })` returns `{ search(q, kind), getPlaylist(id), download(req: DownloadRequest): Promise<{ job: Job } | { duplicate: TrackRecord }>, downloadPlaylist(id, options), convert(paths, options), cancelJob(id), listJobs(), activeCount(), library(q), history(), deleteHistory(ids: number[] | 'all'), getSettings(), putSettings(s), updateYtdlp(), connectEvents(onEvent): () => void }`. HTTP errors become a thrown `EngineError { status, code, message }`. The WS reconnects with backoff (0.5 s → 5 s).
  - `jobsStore` (zustand): `jobs: Record<string, Job>`, `speed/eta` per job, `applyEvent(e: EngineEvent)`, `markEngineReset()` (every queued or running job → `status: 'failed'`, error message `El motor se reinició`), selectors `activeJobs`, `childrenOf(id)`.
  - `uiStore`: `route: 'buscar' | 'descargas' | 'biblioteca' | 'historial' | 'conversor' | 'ajustes'`, `sheet: SheetState | null`, `toasts`, `tinted: boolean`, `theme: 'dark' | 'light'`.
  - `GlassSheet` props `{ title: string; onClose(): void; children; actions?: ReactNode }`: modal centered panel with focus trap, closes on `Esc`.
  - Tokens: copy the `--lg-*` variables from `Liquid_Glass.md` §Color Palette. `[data-theme=light]` overrides. `[data-tinted=true]` sets the glass fill to 0.70 alpha. Fonts through `@fontsource/inter` (400/500/600) and `@fontsource/plus-jakarta-sans` (600/700). Glass is used only in the sidebar, top search pill, MiniQueue, GlassSheet, toasts and pill controls; the content area uses `--lg-slate` at 0.92 alpha.

- [ ] **Step 1: Write failing tests**
```ts
it('sends X-Token and maps 409 duplicate', async () => {
  const fetch = mockFetch(409, { duplicate: { id: 1, title: 'La Graciosa' } });
  const c = createClient({ baseUrl: 'http://x', token: 't' }, fetch);
  expect(await c.download(req)).toEqual({ duplicate: expect.objectContaining({ id: 1 }) });
  expect(fetch.mock.calls[0][1].headers['X-Token']).toBe('t');
});
it('applies progress then done', () => { /* applyEvent queued -> progress 40 -> done; status done, pct 100 */ });
it('engine reset fails active jobs', () => {
  s.applyEvent(progress('a', 40)); s.markEngineReset();
  expect(s.jobs.a.status).toBe('failed'); expect(s.jobs.a.error?.message).toBe('El motor se reinició');
});
```
- [ ] **Step 2: Run** `npx vitest run ui`. Expected: FAIL.
- [ ] **Step 3: Implement** the client, stores and shell. Invoke the `impeccable` skill for the shell layout and glass treatment, and look up any needed rule with the `ui-ux-pro-max` search script. `onEngineState('restarting')` → `markEngineReset()` plus a toast `Reconectando motor…`.
- [ ] **Step 4: Run** `npx vitest run ui`. Expected: pass.
- [ ] **Step 5: Verify visually** with `npm run dev`: take screenshots at 1024×640 and 1920×1080, in dark, light and tinted modes. Check: no text under 14px on glass, at most 2 stacked glass layers, the sidebar reads as heavier glass than the content.
- [ ] **Step 6: Commit** `feat(ui): liquid glass shell, engine client and job store`

---

### Task 12: Search screen, detail sheet, download menu, duplicate dialog

**Files:** Create `ui/src/screens/SearchScreen.tsx`, `ui/src/components/ResultRow.tsx`, `TrackDetailSheet.tsx`, `FormatMenu.tsx`, `DuplicateSheet.tsx`, `ui/src/lib/format.ts`. Test `ui/src/lib/format.test.ts`, `ui/src/screens/SearchScreen.test.tsx`.

**Interfaces:**
- Consumes: `createClient`, `uiStore`, `GlassSheet`.
- Produces: `formatDuration(s: number): string` (`213` → `3:33`, `3725` → `1:02:05`); `formatViews(n: number): string` (`1200000` → `1,2 M`, `350000` → `350 K`, `999` → `999`; Spanish style).
- Behavior:
  - Segmented control `Canciones | Vídeos | Playlists`; the search runs on Enter or after a 400 ms debounce once the query has ≥ 2 characters.
  - Each row shows cover, title, artist, duration, views (hidden when null), a `En tu biblioteca` badge when `in_library`, and the main pill `Descargar` (default format label, e.g. `MP3 320`) with a chevron that opens `FormatMenu` (all formats, plus quality, sample rate and bit depth for lossless formats).
  - When a lossless format is chosen, the menu shows the note `Convertir audio de YouTube a un formato sin pérdida no aumenta su calidad.`
  - Clicking a row opens `TrackDetailSheet` (big cover, data, the same download controls). Playlist rows open a sheet with the track list and the button `Descargar playlist (N)`.
  - On a duplicate response → `DuplicateSheet` titled `Ya tienes esta canción`, with the buttons `Abrir ubicación` (`showInFolder`), `Descargar igualmente` (repeats with `force: true`) and `Cancelar`.
  - Empty states: `Busca una canción, artista o pega un enlace de YouTube` before the first search, and `Sin resultados para "<q>"` after an empty search. Errors show as a toast with the engine message.
  - No BPM/KEY text anywhere in Phase 1.

- [ ] **Step 1: Write failing tests**: the format helpers with the values above; SearchScreen with a mocked client — typing `la graciosa` + Enter renders the rows; clicking `Descargar` on a duplicate opens a sheet with the text `Ya tienes esta canción`; `Descargar igualmente` calls `download` with `force: true`; the DOM never contains `BPM`.
- [ ] **Step 2: Run** `npx vitest run ui/src/screens/SearchScreen.test.tsx ui/src/lib/format.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement** (using the `impeccable` skill for the row and sheet visuals).
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Verify** with `ONEFORALL_FAKE=1 npm run dev`: search, download, then a duplicate download. Take screenshots at 1024×640 and 1920×1080.
- [ ] **Step 6: Commit** `feat(ui): search screen with format menu and duplicate dialog`

---

### Task 13: Downloads screen and MiniQueue (per-job cancel, playlist summary)

**Files:** Create `ui/src/screens/DownloadsScreen.tsx`, `ui/src/components/JobRow.tsx`, `PlaylistSummarySheet.tsx`; modify `MiniQueue.tsx`. Test `ui/src/screens/DownloadsScreen.test.tsx`.

**Interfaces:**
- Consumes: `jobsStore`, `client.cancelJob`, `client.downloadPlaylist` (retry failed tracks = new download jobs for the failed titles).
- Behavior:
  - Each job row shows its title, a stage label (`En cola`, `Descargando`, `Convirtiendo`, `Etiquetando`, `Finalizando`), a progress bar, speed/ETA while downloading, and a `Cancelar` button for that job only. Playlist parents are collapsible and show `X / N` plus a `Cancelar playlist` button.
  - On `job.cancelled`, the bar resets to 0 and every animation stops at once: the progress animation class depends only on `status === 'running'`.
  - Finished rows show `Mostrar en carpeta`. Failed rows show the engine message and `Reintentar`.
  - When a playlist finishes → `PlaylistSummarySheet`: `N descargadas · M fallidas · K ya en tu biblioteca`, the list of failures with reasons, and `Reintentar fallidas`.
  - MiniQueue (glass, bottom of the window): count of active jobs and total progress; clicking it navigates to Descargas.

- [ ] **Step 1: Write failing tests**: with the store seeded with two running jobs, clicking `Cancelar` on job A calls `cancelJob('A')` only; after a `job.cancelled` event the row for A has no element with the class `is-animating` and shows `Cancelado`; a playlist done event with `{done: 8, failed: [1 item], skipped: 1}` opens a sheet containing `8 descargadas · 1 fallidas · 1 ya en tu biblioteca`.
- [ ] **Step 2: Run** `npx vitest run ui/src/screens/DownloadsScreen.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** `feat(ui): downloads queue with per-job cancel and playlist summary`

---

### Task 14: Library and History screens

**Files:** Create `ui/src/screens/LibraryScreen.tsx`, `ui/src/screens/HistoryScreen.tsx`, `ui/src/components/SelectableTable.tsx`. Test `ui/src/screens/HistoryScreen.test.tsx`, `ui/src/screens/LibraryScreen.test.tsx`.

**Interfaces:**
- Consumes: `client.library`, `client.history`, `client.deleteHistory`, preload `showInFolder` / `openPath`.
- Produces: `SelectableTable<T>` props `{ rows: T[]; columns: Column<T>[]; selected: Set<number>; onSelect(ids: Set<number>): void; rowId(r: T): number }`, supporting click, Ctrl+click, Shift+click and select-all.
- Behavior:
  - Library: filter field; columns Título, Artista, Duración, Visualizaciones, Formato, Añadida. Rows with `missing` show the badge `No encontrado` and grey text. Double-click → `openPath`. The context action is `Mostrar en carpeta`.
  - History: columns Título, Artista, Acción (`Descarga` / `Conversión`), Estado, Fecha. Toolbar `Borrar seleccionadas (N)` (disabled at 0) and `Borrar todo`, which opens a GlassSheet confirm with the text `¿Borrar todo el historial? Los archivos no se borran.`
  - The list refreshes on `job.done` events.

- [ ] **Step 1: Write failing tests**: select 2 rows → click `Borrar seleccionadas (2)` → `deleteHistory([id1, id2])`; `Borrar todo` → confirm sheet → `deleteHistory('all')`; a library row with `missing: true` shows `No encontrado`.
- [ ] **Step 2: Run** `npx vitest run ui/src/screens/HistoryScreen.test.tsx ui/src/screens/LibraryScreen.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** `feat(ui): library and history with selective delete`

---

### Task 15: Converter and Settings screens

**Files:** Create `ui/src/screens/ConverterScreen.tsx`, `ui/src/screens/SettingsScreen.tsx`. Test `ui/src/screens/ConverterScreen.test.tsx`, `ui/src/screens/SettingsScreen.test.tsx`.

**Interfaces:**
- Consumes: `client.convert`, `client.getSettings/putSettings/updateYtdlp`, preload `pathForFile`, `pickFolder`, `uiStore.tinted/theme`.
- Behavior:
  - Converter: a drop zone (`Arrastra archivos de audio aquí`) plus an `Elegir de la biblioteca` picker. The file list can remove items. Choose a format with the same `FormatMenu` from Task 12, then `Convertir (N)`, which creates one job per file (visible in Descargas). Non-audio extensions are rejected with a toast. Accepted: `mp3 m4a aac wav aif aiff flac ogg opus webm`.
  - Settings: music folder (`Cambiar…` → `pickFolder`), default format and quality, name template with a live preview (`Quevedo - La Graciosa.mp3`), parallel downloads 1–6, theme Oscuro/Claro, `Modo tintado` switch, `Actualizar yt-dlp` (shows the result text), `Abrir carpeta de logs`. Changes save immediately through `putSettings`; theme and tinted mode also persist in settings (`tinted`) and apply to `<html data-theme data-tinted>`.

- [ ] **Step 1: Write failing tests**: dropping two files (mock `pathForFile`) and choosing FLAC → `convert(['C:/a.mp3','C:/b.wav'], {format:'flac'})`; dropping `x.txt` → toast and no call; toggling `Modo tintado` sets `data-tinted="true"` on `<html>` and calls `putSettings` with `tinted: true`; the template preview updates when the template changes.
- [ ] **Step 2: Run** `npx vitest run ui/src/screens/ConverterScreen.test.tsx ui/src/screens/SettingsScreen.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Verify visually**: screenshots of every screen at 1024×640 and 1920×1080, in dark, light and tinted modes. Run the `impeccable` audit or polish pass and fix what it reports.
- [ ] **Step 6: Commit** `feat(ui): converter and settings screens`

---

### Task 16: End-to-end tests (Playwright on Electron, fake engine)

**Files:** Create `e2e/app.spec.ts`, `playwright.config.ts`.

**Interfaces:**
- Consumes: the built app (`npm run build`) launched with `_electron.launch({ args: ['.'], env: { ONEFORALL_FAKE: '1', ONEFORALL_DATA_ROOT: <tmp>, ONEFORALL_MUSIC_DIR: <tmp>/music } })`. Add support for `ONEFORALL_DATA_ROOT` / `ONEFORALL_MUSIC_DIR` in Task 10's main (passed as `--data-root` and as a settings override) if they are not there yet.

- [ ] **Step 1: Write the tests**
  - `search → download → library`: search `graciosa`, click `Descargar`, wait for `Mostrar en carpeta` in Descargas; the file `Fake Artist - La Graciosa.mp3` exists in the music dir; Biblioteca shows the row.
  - `duplicate → force → (1)`: repeat the download, `Descargar igualmente`; `… (1).mp3` exists in the same dir and there are no subdirectories.
  - `cancel leaves nothing`: start a download, cancel at once; the music dir has no new file and `<data>/tmp` is empty.
  - `playlist summary`: download the fake playlist; the summary shows `1 fallidas`.
  - `close guard`: start a download and trigger window close; the dialog text contains `procesos en curso` (stub `dialog.showMessageBox` through `electronApp.evaluate` to capture the message and answer `Cancelar`).
- [ ] **Step 2: Run** `npm run build; npx playwright test`. Expected: 5 passed. Fix the app code (not the tests) until they pass.
- [ ] **Step 3: Commit** `test(e2e): electron flows with fake engine`

---

### Task 17: Windows packaging

**Files:** Create `build/fetch-runtime.ps1`, `electron-builder.yml`; modify `package.json` (`dist` script).

**Interfaces:**
- Produces: `build/runtime/python/` (python-3.12 embeddable amd64 with `python312._pth` edited to enable `import site` and `Lib/site-packages`, engine installed with `pip install --target`), `build/runtime/bin/ffmpeg.exe`, `ffprobe.exe` (gyan.dev release essentials build) and `yt-dlp.exe` (latest GitHub release). electron-builder `extraResources: build/runtime → runtime`, NSIS target, `appId: com.oneforall.app`, `productName: OneForAll`, per-user install, desktop shortcut.
- yt-dlp self-update in packaged mode: the `yt-dlp.exe -U` binary lives in `runtime/bin`, which sits under the per-user install dir, so it is writable.

- [ ] **Step 1: Write** `fetch-runtime.ps1` (idempotent; verifies SHA256 when the release page publishes it; downloads to `build/runtime/`).
- [ ] **Step 2: Run** `pwsh build/fetch-runtime.ps1; npm run dist`. Expected: `dist/OneForAll Setup <version>.exe` is created.
- [ ] **Step 3: Verify the packaged app** by installing and launching it, then running a real search and download of a song (online). To prove it works without system tools, temporarily rename the system `ffmpeg` so it is off PATH, or test in Windows Sandbox. Expected: the download completes and the engine log shows the bundled tool paths.
- [ ] **Step 4: Run the full suite**: `cd engine; uv run pytest`; `npx vitest run`; `npx playwright test`. Expected: all pass.
- [ ] **Step 5: Commit** `build: windows installer with embedded python, ffmpeg and yt-dlp`

---

## Acceptance check (spec §11)

| # | Criterion | Covered by |
|---|---|---|
| 1 | Search "la graciosa quevedo" → song in top results | Task 8 online test, Task 17 step 3 |
| 2 | `Artista - Título.mp3` 320 with cover, in library and history | Task 9, Task 16 |
| 3 | Duplicate warning; force → `(1)` same folder | Task 9, Task 12, Task 16 |
| 4 | Playlist continues on failure, summary | Task 9, Task 13, Task 16 |
| 5 | Cancel leaves no files and doesn't affect others | Task 4, Task 9, Task 13, Task 16 |
| 6 | Close warning with active jobs | Task 10, Task 16 |
| 7 | Convert to FLAC/WAV/AIFF/OPUS/M4A | Task 5, Task 15 |
| 8 | History delete selected / all | Task 3, Task 14 |
| 9 | Installer works without Python/ffmpeg | Task 17 |
