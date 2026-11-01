import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Annotated, Any, Callable, Literal, Union

from fastapi import APIRouter, Body, Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .app_paths import AppPaths
from .convert import ConvertOptions
from .download import download_audio, ytdlp_cmd
from .jobs import JobManager
from .library import Library
from .pipelines import DownloadRequest, make_convert_runner, make_download_runner, start_playlist
from .search import SearchService
from .settings import Settings, load_settings, save_settings

log = logging.getLogger(__name__)
CONVERT_CONCURRENCY = 2


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
    shutdown: Callable[[], None] | None = None


def build_services(paths: AppPaths, fake: bool) -> Services:
    settings = load_settings(paths.settings_path)
    hub = EventHub()
    jobs = JobManager(paths.tmp_dir, hub.broadcast, {"download": settings.download_concurrency, "convert": CONVERT_CONCURRENCY})
    jobs.purge_orphans()
    library = Library(paths.db_path)
    library.refresh_missing()
    if fake:
        from .fakes import FakeSearch, fake_downloader

        search, downloader = FakeSearch(), fake_downloader
    else:
        search, downloader = SearchService(), download_audio
    return Services(paths, settings, library, jobs, search, downloader, fake, hub)


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


JobBody = Annotated[Union[DownloadJobBody, PlaylistJobBody, ConvertJobBody], Field(discriminator="type")]


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
        return [asdict(h) for h in svc.library.list_history()]

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
