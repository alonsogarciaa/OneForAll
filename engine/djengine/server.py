import asyncio
import logging
import os
import threading
import secrets
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Annotated, Any, Callable, Literal, Union

from fastapi import APIRouter, Body, Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from .app_paths import AppPaths
from .convert import ConvertOptions
from .download import download_audio, ytdlp_cmd
from .jobs import JobManager
from .library import Library
from .analysis.config import ANALYSIS_VERSION as ANALYSIS_VERSION_NOW
from .mixer.state import MixState
from .pipelines import (DownloadRequest, make_convert_runner, make_download_runner, start_playlist, submit_analysis,
                        submit_stems)
from .search import SearchService
from .settings import Settings, load_settings, save_settings

log = logging.getLogger(__name__)
CONVERT_CONCURRENCY = 2
ANALYSIS_CONCURRENCY = 2


class EventHub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def broadcast(self, event: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(event)
            except Exception:
                self.clients.discard(ws)


@dataclass
class Services:
    paths: AppPaths
    settings: Settings
    library: Any
    jobs: Any
    search: Any
    downloader: Any
    fake: bool
    hub: EventHub = field(default_factory=EventHub)
    analysis: Any = None
    stems: Any = None
    mixer: Any = None
    allowed_paths: set = field(default_factory=set)  # files the user picked this session (/audio)
    shutdown: Callable[[], None] | None = None


def _tools_on_path() -> None:
    """Some libraries (audio-separator) run "ffmpeg" by name: expose the bundled tools dir once, at startup."""
    from .errors import UserError as _UE
    from .tools import find_tool

    try:
        tools = str(Path(find_tool("ffmpeg")).parent)
    except _UE:
        return
    if tools not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = tools + os.pathsep + os.environ.get("PATH", "")


def build_services(paths: AppPaths, fake: bool) -> Services:
    settings = load_settings(paths.settings_path)
    hub = EventHub()
    jobs = JobManager(paths.tmp_dir, hub.broadcast, {"download": settings.download_concurrency, "convert": CONVERT_CONCURRENCY, "analysis": ANALYSIS_CONCURRENCY, "stems": 1, "mix_export": 1, "retempo": 1})
    jobs.purge_orphans()
    _tools_on_path()
    from .pipelines import sweep_parts

    threading.Thread(target=sweep_parts, args=([settings.music_dir, getattr(settings, "stems_dir", None) or settings.music_dir],),
                     name="sweep-parts", daemon=True).start()
    library = Library(paths.db_path)
    library.refresh_missing()
    if fake:
        from .fakes import FakeSearch, fake_downloader

        search, downloader = FakeSearch(), fake_downloader
    else:
        search, downloader = SearchService(), download_audio
    from .analysis.store import AnalysisStore

    from .mixer.state import MixerStore
    from .stems.store import StemsStore

    analysis = AnalysisStore(paths.db_path, paths.root / "analysis")
    return Services(paths, settings, library, jobs, search, downloader, fake, hub, analysis=analysis,
                    stems=StemsStore(paths.db_path), mixer=MixerStore(paths.db_path))


# --- request bodies -----------------------------------------------------------
class DownloadJobBody(BaseModel):
    type: Literal["download"]
    request: DownloadRequest
    dest_dir: str | None = None  # retry of a playlist track: back into its playlist folder
    playlist_id: int | None = None
    position: int | None = None


class PlaylistJobBody(BaseModel):
    type: Literal["playlist"]
    id: str
    options: ConvertOptions


class ConvertJobBody(BaseModel):
    type: Literal["convert"]
    paths: list[str] = Field(min_length=1)
    options: ConvertOptions


class AnalysisJobBody(BaseModel):
    type: Literal["analysis"]
    paths: list[str] = Field(min_length=1)
    force: bool = False
    reset_bpm: bool = False


class StemsJobBody(BaseModel):
    type: Literal["stems"]
    paths: list[str] = Field(min_length=1)
    stems: list[str] = Field(min_length=1)
    karaoke: bool = False

    @field_validator("stems")
    @classmethod
    def _known(cls, v):
        from .stems.names import STEMS

        bad = [s for s in v if s not in STEMS]
        if bad:
            raise ValueError(f"stem desconocido: {bad[0]}")
        return v


class ZipBody(BaseModel):
    path: str


class MixerStateBody(BaseModel):
    path: str
    state: MixState


class SectionIn(BaseModel):
    start: float = Field(ge=0)
    end: float
    label: str


class SectionsEdit(BaseModel):
    path: str
    sections: list[SectionIn] | None = Field(default=None, max_length=64)
    reset: bool = False


class GridEdit(BaseModel):
    path: str
    anchor: float | None = Field(default=None, ge=0)
    bpm: float | None = Field(default=None, gt=20, lt=400)
    shift_ms: float | None = Field(default=None, ge=-2000, le=2000)
    shift_beats: int | None = Field(default=None, ge=-64, le=64)
    scale: Literal[0.5, 2] | None = None
    reset: bool = False


class ManualBpm(BaseModel):
    path: str
    bpm: float = Field(gt=20, lt=400)


class MixExportJobBody(BaseModel):
    type: Literal["mix_export"]
    path: str
    state: MixState
    range: Literal["full", "loop"] = "full"
    format: Literal["wav16", "wav24", "flac", "mp3"] | None = None


class RetempoJobBody(BaseModel):
    type: Literal["retempo"]
    path: str
    bpm: float = Field(gt=20, lt=400)
    semis: int = Field(ge=-12, le=12)
    format: Literal["wav16", "wav24", "flac", "mp3"] | None = None


JobBody = Annotated[Union[DownloadJobBody, PlaylistJobBody, ConvertJobBody, AnalysisJobBody, StemsJobBody, MixExportJobBody, RetempoJobBody],
                    Field(discriminator="type")]

AUDIO_EXT = {".mp3", ".m4a", ".aac", ".wav", ".aif", ".aiff", ".flac", ".ogg", ".opus", ".webm"}
LEVEL_ORDER = {"same": 0, "adjacent": 1, "relative": 2}


def _audio_info(path: Path) -> dict:
    import mutagen

    try:
        f = mutagen.File(path)
        info = f.info if f is not None else None
    except Exception:
        info = None
    return {
        "format": path.suffix.lstrip(".").lower(),
        "bitrate": int(getattr(info, "bitrate", 0) or 0) // 1000 or None,
        "sample_rate": getattr(info, "sample_rate", None),
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def _norm(p: str | Path) -> str:
    return os.path.normcase(os.path.realpath(str(p)))


class HistoryDelete(BaseModel):
    ids: list[int] | None = None
    all: bool = False


def create_app(services: Services, token: str) -> FastAPI:
    svc = services

    def require_token(x_token: str | None = Header(default=None)) -> None:
        if not x_token or not secrets.compare_digest(x_token, token):
            raise HTTPException(status_code=401, detail="unauthorized")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await svc.jobs.cancel_all()

    app = FastAPI(lifespan=lifespan)
    # The Electron renderer loads from file:// (origin "null") or the dev server on localhost.
    # Web pages never get the token, but they are still kept out of CORS.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(null|http://localhost:\d+)$",
        allow_methods=["*"],
        allow_headers=["X-Token", "Content-Type"],
    )
    app.state.services = svc
    api = APIRouter(dependencies=[Depends(require_token)])

    @api.get("/health")
    def health():
        return {"ok": True}

    @api.get("/info")
    def info():
        return {"logs_dir": str(svc.paths.logs_dir), "data_dir": str(svc.paths.root)}

    @api.get("/settings")
    def get_settings():
        return svc.settings.model_dump()

    @api.put("/settings")
    def put_settings(s: Settings):
        svc.settings = s
        save_settings(svc.paths.settings_path, s)
        svc.jobs.set_concurrency("download", s.download_concurrency)
        return s.model_dump()

    @api.get("/search")
    async def search(q: str, kind: Literal["songs", "videos", "playlists"] = "songs"):
        try:
            results = await asyncio.to_thread(svc.search.search, q, kind)
        except Exception as e:
            log.warning("search failed: %s", e)
            raise HTTPException(status_code=502, detail={"code": "offline", "message": "No se pudo buscar. Revisa tu conexión."})
        for r in results:
            if r.kind != "playlist":
                r.in_library = svc.library.find_duplicate(r.id, r.artist, r.title) is not None
        return [r.model_dump() for r in results]

    @api.get("/playlist/{playlist_id}")
    async def playlist(playlist_id: str):
        try:
            info = await asyncio.to_thread(svc.search.get_playlist, playlist_id)
        except Exception as e:
            log.warning("playlist fetch failed: %s", e)
            raise HTTPException(status_code=502, detail={"code": "offline", "message": "No se pudo cargar la playlist."})
        for t in info.tracks:
            t.in_library = svc.library.find_duplicate(t.id, t.artist, t.title) is not None
        return info.model_dump()

    @api.post("/jobs")
    async def create_job(body: JobBody = Body(...)):
        if isinstance(body, DownloadJobBody):
            t = body.request.target
            if not body.request.force:
                dup = svc.library.find_duplicate(t.id, t.artist, t.title)
                if dup is not None:
                    return JSONResponse(status_code=409, content={"duplicate": asdict(dup)})
            dest = Path(svc.settings.music_dir)
            if body.dest_dir:
                music = os.path.normcase(os.path.realpath(svc.settings.music_dir))
                want = os.path.normcase(os.path.realpath(body.dest_dir))
                try:
                    inside = os.path.commonpath([music, want]) == music
                except ValueError:  # other drive
                    inside = False
                if not inside:
                    raise HTTPException(status_code=422, detail={"code": "bad_request", "message": "Carpeta de destino no válida"})
                dest = Path(body.dest_dir)
            runner = make_download_runner(svc, body.request, dest, body.playlist_id, body.position)
            payload = {"request": body.request.model_dump(), "dest_dir": body.dest_dir,
                       "playlist_id": body.playlist_id, "position": body.position}
            return {"job": svc.jobs.submit("download", t.title, runner, payload=payload).to_dict()}
        if isinstance(body, PlaylistJobBody):
            try:
                job = await start_playlist(svc, body.id, body.options)
            except Exception as e:
                log.warning("playlist start failed: %s", e)
                raise HTTPException(status_code=502, detail={"code": "offline", "message": "No se pudo cargar la playlist."})
            return {"job": job.to_dict()}
        if isinstance(body, RetempoJobBody):
            from .errors import UserError as _UE
            from .prep.retempo import check_range, make_retempo_runner

            src = svc.analysis.get(Path(body.path))
            if src is None or not src.bpm:
                raise HTTPException(status_code=409, detail={"code": "not_analyzed", "message": "Analiza primero"})
            try:
                check_range(src.bpm, body.bpm)
            except _UE as e:
                raise HTTPException(status_code=422, detail={"code": e.code, "message": e.message})
            runner = make_retempo_runner(svc, Path(body.path), body.bpm, body.semis, body.format)
            return {"job": svc.jobs.submit("retempo", f"Cambiar BPM · {Path(body.path).stem}", runner,
                                           payload=body.model_dump()).to_dict()}
        if isinstance(body, MixExportJobBody):
            from .mixer.export import make_mix_export_runner

            if body.range == "loop" and body.state.loop is None:
                raise HTTPException(status_code=422, detail={"code": "bad_request", "message": "No hay bucle"})
            runner = make_mix_export_runner(svc, Path(body.path), body.state, body.range, body.format)
            return {"job": svc.jobs.submit("mix_export", f"Exportar · {Path(body.path).stem}", runner,
                                           payload=body.model_dump()).to_dict()}
        if isinstance(body, StemsJobBody):
            for p in body.paths:
                svc.allowed_paths.add(_norm(p))
            return {"jobs": [submit_stems(svc, Path(p), body.stems, body.karaoke).to_dict() for p in body.paths]}
        if isinstance(body, AnalysisJobBody):
            for p in body.paths:
                svc.allowed_paths.add(_norm(p))
            return {"jobs": [submit_analysis(svc, Path(p), force=body.force, reset_bpm=body.reset_bpm).to_dict() for p in body.paths]}
        jobs = [
            svc.jobs.submit("convert", Path(p).name, make_convert_runner(svc, Path(p), body.options),
                            payload={"paths": [p], "options": body.options.model_dump()}).to_dict()
            for p in body.paths
        ]
        return {"jobs": jobs}

    @api.get("/jobs")
    def list_jobs():
        return [j.to_dict() for j in svc.jobs.list()]

    @api.get("/jobs/active-count")
    def active_count():
        return {"count": svc.jobs.active_count(), "by_type": svc.jobs.active_by_type()}

    @api.delete("/jobs/{job_id}")
    async def cancel_job(job_id: str):
        return {"cancelled": await svc.jobs.cancel(job_id)}

    @api.get("/analysis")
    def get_analysis(path: str):
        rec = svc.analysis.get(Path(path))
        if rec is None:
            raise HTTPException(status_code=404, detail={"code": "not_analyzed", "message": "Sin analizar"})
        side = dict(svc.analysis.get_sidecar(Path(path)) or {})
        side["grid"] = svc.analysis.get_grid(Path(path)).to_dict()
        side.setdefault("sections", [])
        side["needs_reanalysis"] = rec.version < ANALYSIS_VERSION_NOW
        return {"record": asdict(rec), "sidecar": side, "info": _audio_info(Path(path))}

    @api.put("/analysis/bpm")
    def manual_bpm(body: ManualBpm):
        from .analysis.runner import write_analysis_tags
        from .analysis.store import file_stamp

        p = Path(body.path)
        if svc.analysis.get_any(p) is None:
            raise HTTPException(status_code=404, detail={"code": "not_analyzed", "message": "Sin analizar"})
        if svc.analysis.get(p) is None:  # file changed since: re-blessing the old record would be wrong
            raise HTTPException(status_code=409, detail={"code": "stale", "message": "El archivo ha cambiado: reanalízalo primero"})
        from .prep.grid import edit_grid

        rec = svc.analysis.set_manual_bpm(p, body.bpm)
        svc.analysis.save_grid(p, edit_grid(svc.analysis.get_grid(p), bpm=rec.bpm))
        before = file_stamp(p)
        if write_analysis_tags(p, rec.bpm, None):  # BPM only; key and other tags untouched
            svc.analysis.restamp(p)
            svc.stems.restamp(p, before)
        track = svc.library.track_by_path(str(p))
        if track:
            svc.library.set_track_analysis(str(p), rec.bpm, track.musical_key, track.camelot, track.lufs)
        return asdict(svc.analysis.get_any(p))

    def _bpm_to_tags(p: Path, bpm: float) -> None:
        from .analysis.runner import write_analysis_tags
        from .analysis.store import file_stamp

        before = file_stamp(p)
        if write_analysis_tags(p, bpm, None):  # BPM only; key and other tags untouched
            svc.analysis.restamp(p)
            svc.stems.restamp(p, before)
        track = svc.library.track_by_path(str(p))
        if track:
            svc.library.set_track_analysis(str(p), bpm, track.musical_key, track.camelot, track.lufs)

    @api.put("/analysis/sections")
    def put_sections(body: SectionsEdit):
        from .prep.sections import LABELS, Section

        p = Path(body.path)
        if svc.analysis.get_any(p) is None:
            raise HTTPException(status_code=404, detail={"code": "not_analyzed", "message": "Sin analizar"})
        if svc.analysis.get(p) is None:
            raise HTTPException(status_code=409, detail={"code": "stale", "message": "El archivo ha cambiado: reanalízalo primero"})
        side = svc.analysis.read_sidecar(p) or {}
        if body.reset:
            out = [Section.from_dict(d) for d in side.get("sections_auto") or []]
        else:
            duration = float(side.get("duration") or 0)
            items = body.sections or []
            prev_end = 0.0
            for it in items:
                bad = (it.label not in LABELS or it.end <= it.start or it.start < prev_end - 1e-6
                       or it.end > duration + 1e-3)
                if bad:
                    raise HTTPException(status_code=422, detail={"code": "bad_request", "message": "Secciones no válidas"})
                prev_end = it.end
            out = [Section(round(it.start, 3), round(it.end, 3), it.label, "manual") for it in items]
        svc.analysis.save_sections(p, out)
        return {"sections": [x.to_dict() for x in out]}

    @api.put("/analysis/grid")
    def put_grid(body: GridEdit):
        from .prep.grid import Grid, edit_grid

        p = Path(body.path)
        if svc.analysis.get_any(p) is None:
            raise HTTPException(status_code=404, detail={"code": "not_analyzed", "message": "Sin analizar"})
        if svc.analysis.get(p) is None:
            raise HTTPException(status_code=409, detail={"code": "stale", "message": "El archivo ha cambiado: reanalízalo primero"})
        current = svc.analysis.get_grid(p)
        rec = svc.analysis.get_any(p)
        if body.reset:
            auto = (svc.analysis.read_sidecar(p) or {}).get("grid_auto")
            grid = Grid.from_dict(auto) if auto else Grid(current.anchor, current.bpm, "auto")
            grid = Grid(grid.anchor, float(rec.bpm if rec.bpm_source == "auto" else grid.bpm), "auto")
            if rec.bpm_source != "auto" or rec.bpm != grid.bpm:
                svc.analysis.set_bpm(p, grid.bpm, "auto")
        else:
            grid = edit_grid(current, anchor=body.anchor, bpm=body.bpm, shift_ms=body.shift_ms,
                             shift_beats=body.shift_beats, scale=body.scale)
            if round(grid.bpm, 1) != (rec.bpm or 0):
                svc.analysis.set_manual_bpm(p, grid.bpm)
        svc.analysis.save_grid(p, grid)
        if round(grid.bpm, 1) != (rec.bpm or 0):
            _bpm_to_tags(p, round(grid.bpm, 1))
        return {"grid": grid.to_dict()}

    class StemCheck(BaseModel):
        files: list[str] = Field(max_length=64)

    @api.post("/stems/check")
    def check_stems(body: StemCheck):
        """Which of these files are stems we produced (the app only lets those be dragged out)."""
        return {"stems": [f for f in body.files if svc.stems.is_stem_file(f) or svc.mixer.is_export(f)]}

    @api.get("/mixer/state")
    def get_mixer_state(path: str):
        st = svc.mixer.get(path)
        return {"state": st.model_dump() if st else None}

    @api.put("/mixer/state")
    def put_mixer_state(body: MixerStateBody):
        svc.mixer.put(body.path, body.state)
        return {"ok": True}

    @api.get("/stems/backend")
    def stems_backend():
        from .stems.accel import backend

        return {"backend": backend(svc.settings)}

    @api.get("/stems")
    def list_stems(path: str):
        got = svc.stems.get(Path(path))
        return {
            "folder": str(next(iter(got.values())).parent) if got else None,
            "stems": [{"stem": k, "file": str(v), "size_bytes": v.stat().st_size} for k, v in got.items()],
        }

    zip_lock = threading.Lock()

    @api.post("/stems/zip")
    def zip_stems(body: ZipBody):
        import zipfile

        got = svc.stems.get(Path(body.path))
        if not got:
            raise HTTPException(status_code=404, detail={"code": "no_stems", "message": "Esta canción no tiene stems"})
        folder = next(iter(got.values())).parent
        import uuid

        dst = folder / f"{folder.name} (stems).zip"
        tmp = folder / f"~oneforall-{uuid.uuid4().hex}.part"
        with zip_lock:  # Windows refuses os.replace onto a file another request is replacing
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
                for f in got.values():
                    z.write(f, arcname=f.name)
            os.replace(tmp, dst)
        return {"zip": str(dst)}

    @api.get("/harmonic")
    def harmonic(ref_track: int | None = None, bpm: float | None = None, camelot: str | None = None,
                 bpm_tolerance: float = Query(default=6, gt=0, le=20)):
        from .analysis.camelot import compatible

        tracks = [t for t in svc.library.list_tracks() if t.bpm and t.camelot and not t.missing]
        if ref_track is not None:
            ref = next((t for t in tracks if t.id == ref_track), None)
            if ref is None:
                raise HTTPException(status_code=404, detail={"code": "not_analyzed", "message": "La pista de referencia no está analizada"})
            bpm, camelot = ref.bpm, ref.camelot
        if not bpm or not camelot:
            raise HTTPException(status_code=422, detail={"code": "bad_request", "message": "Indica una pista o BPM y tonalidad"})
        from .analysis.camelot import _FROM

        if camelot.upper() not in _FROM:
            raise HTTPException(status_code=422, detail={"code": "bad_request", "message": "Tonalidad Camelot no válida"})
        camelot = camelot.upper()
        out = []
        for t in tracks:
            if t.id == ref_track:
                continue
            level = compatible(camelot, t.camelot)
            if level is None:
                continue
            diff = min(((t.bpm * f - bpm) / bpm * 100 for f in (1, 2, 0.5)), key=abs)
            if abs(diff) <= bpm_tolerance:
                out.append({"track": asdict(t), "level": level, "bpm_diff_pct": round(diff, 1)})
        out.sort(key=lambda r: (LEVEL_ORDER[r["level"]], abs(r["bpm_diff_pct"])))
        return out

    @api.get("/library")
    def library(q: str = ""):
        svc.library.refresh_missing()
        from .stems.store import key as stem_key

        with_stems = svc.stems.sources_with_stems()
        return [{**asdict(t), "has_stems": stem_key(t.path) in with_stems and bool(svc.stems.get(Path(t.path)))}
                for t in svc.library.list_tracks(q)]

    @api.get("/library/duplicate")
    def duplicate(videoId: str | None = None, artist: str = "", title: str = ""):
        dup = svc.library.find_duplicate(videoId, artist, title)
        return {"duplicate": asdict(dup) if dup else None}

    @api.get("/history")
    def history():
        tracks = {t.id: t for t in svc.library.list_tracks()}
        rows = []
        for h in svc.library.list_history():
            t = tracks.get(h.track_id)
            rows.append({**asdict(h), "bpm": t.bpm if t else None, "camelot": t.camelot if t else None,
                         "path": t.path if t else None})
        return rows

    @api.delete("/history")
    def delete_history(body: HistoryDelete):
        if body.all:
            return {"deleted": svc.library.delete_history(None)}
        return {"deleted": svc.library.delete_history(body.ids or [])}

    @api.post("/tools/ytdlp/update")
    async def update_ytdlp():
        proc = await asyncio.create_subprocess_exec(
            *ytdlp_cmd(), "-U", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        out, _ = await proc.communicate()
        return {"ok": proc.returncode == 0, "output": out.decode("utf-8", "replace")[-4000:]}

    @api.post("/shutdown")
    async def shutdown():
        await svc.jobs.cancel_all()
        if svc.shutdown:
            asyncio.get_running_loop().call_later(0.1, svc.shutdown)
        return {"ok": True}

    app.include_router(api)

    @app.get("/audio")
    def audio(path: str, token_q: str | None = Query(default=None, alias="token")):
        # <audio> elements cannot send headers, so the token travels in the query string
        if not token_q or not secrets.compare_digest(token_q, token):
            raise HTTPException(status_code=401, detail="unauthorized")
        real = _norm(path)
        if Path(real).suffix.lower() not in AUDIO_EXT or not Path(real).is_file():
            raise HTTPException(status_code=403, detail="forbidden")
        cands = {path, os.path.realpath(path), str(Path(path)), str(Path(os.path.realpath(path)))}
        allowed = (real in svc.allowed_paths or svc.stems.is_stem_file(real)
                   or any(svc.analysis.get_any(Path(c)) for c in cands)
                   or any(svc.library.track_by_path(c) for c in cands))
        if not allowed:
            raise HTTPException(status_code=403, detail="forbidden")
        return FileResponse(real)

    @app.websocket("/events")
    async def events(ws: WebSocket, token_q: str | None = Query(default=None, alias="token")):
        if not token_q or not secrets.compare_digest(token_q, token):
            await ws.close(code=4401)
            return
        await ws.accept()
        svc.hub.clients.add(ws)
        try:
            await ws.send_json({"type": "engine.hello"})
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            svc.hub.clients.discard(ws)

    return app
