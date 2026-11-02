import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Annotated, Any, Callable, Literal, Union

from fastapi import APIRouter, Body, Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .app_paths import AppPaths
from .convert import ConvertOptions
from .download import download_audio, ytdlp_cmd
from .jobs import JobManager
from .library import Library
from .pipelines import DownloadRequest, make_convert_runner, make_download_runner, start_playlist, submit_analysis
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
    allowed_paths: set = field(default_factory=set)  # files the user picked this session (/audio)
    shutdown: Callable[[], None] | None = None


def build_services(paths: AppPaths, fake: bool) -> Services:
    settings = load_settings(paths.settings_path)
    hub = EventHub()
    jobs = JobManager(paths.tmp_dir, hub.broadcast, {"download": settings.download_concurrency, "convert": CONVERT_CONCURRENCY, "analysis": ANALYSIS_CONCURRENCY})
    jobs.purge_orphans()
    library = Library(paths.db_path)
    library.refresh_missing()
    if fake:
        from .fakes import FakeSearch, fake_downloader

        search, downloader = FakeSearch(), fake_downloader
    else:
        search, downloader = SearchService(), download_audio
    from .analysis.store import AnalysisStore

    analysis = AnalysisStore(paths.db_path, paths.root / "analysis")
    return Services(paths, settings, library, jobs, search, downloader, fake, hub, analysis=analysis)


# --- request bodies -----------------------------------------------------------
class DownloadJobBody(BaseModel):
    type: Literal["download"]
    request: DownloadRequest


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


class ManualBpm(BaseModel):
    path: str
    bpm: float = Field(gt=20, lt=400)


JobBody = Annotated[Union[DownloadJobBody, PlaylistJobBody, ConvertJobBody, AnalysisJobBody], Field(discriminator="type")]

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
            runner = make_download_runner(svc, body.request, Path(svc.settings.music_dir))
            payload = {"request": body.request.model_dump()}
            return {"job": svc.jobs.submit("download", t.title, runner, payload=payload).to_dict()}
        if isinstance(body, PlaylistJobBody):
            try:
                job = await start_playlist(svc, body.id, body.options)
            except Exception as e:
                log.warning("playlist start failed: %s", e)
                raise HTTPException(status_code=502, detail={"code": "offline", "message": "No se pudo cargar la playlist."})
            return {"job": job.to_dict()}
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
        return {"record": asdict(rec), "sidecar": svc.analysis.get_sidecar(Path(path)), "info": _audio_info(Path(path))}

    @api.put("/analysis/bpm")
    def manual_bpm(body: ManualBpm):
        from .analysis.runner import write_analysis_tags

        p = Path(body.path)
        if svc.analysis.get_any(p) is None:
            raise HTTPException(status_code=404, detail={"code": "not_analyzed", "message": "Sin analizar"})
        rec = svc.analysis.set_manual_bpm(p, body.bpm)
        if write_analysis_tags(p, rec.bpm, None):
            svc.analysis.restamp(p)
        track = svc.library.track_by_path(str(p))
        if track:
            svc.library.set_track_analysis(str(p), rec.bpm, track.musical_key, track.camelot, track.lufs)
        return asdict(svc.analysis.get_any(p))

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
        return [asdict(t) for t in svc.library.list_tracks(q)]

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
        allowed = real in svc.allowed_paths or real in {_norm(p) for p in svc.analysis.paths()}             or real in {_norm(t.path) for t in svc.library.list_tracks()}
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
