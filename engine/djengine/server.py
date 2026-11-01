import secrets
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException

from .app_paths import AppPaths
from .settings import Settings, save_settings


@dataclass
class Services:
    paths: AppPaths
    settings: Settings
    library: Any
    jobs: Any
    search: Any
    downloader: Any
    fake: bool


def create_app(services: Services, token: str) -> FastAPI:
    def require_token(x_token: str | None = Header(default=None)) -> None:
        if not x_token or not secrets.compare_digest(x_token, token):
            raise HTTPException(status_code=401, detail="unauthorized")

    app = FastAPI(dependencies=[Depends(require_token)])
    app.state.services = services
    app.state.token = token

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/settings")
    def get_settings():
        return services.settings.model_dump()

    @app.put("/settings")
    def put_settings(s: Settings):
        services.settings = s
        save_settings(services.paths.settings_path, s)
        return s.model_dump()

    return app
