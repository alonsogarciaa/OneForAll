import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger(__name__)


def _default_music_dir() -> str:
    return str(Path.home() / "Music" / "OneForAll")


class Settings(BaseModel):
    music_dir: str = Field(default_factory=_default_music_dir)
    default_format: str = "mp3"
    default_quality: str = "320"
    name_template: str = "{artist} - {title}"
    download_concurrency: int = Field(default=3, ge=1, le=6)
    tinted: bool = False


def load_settings(path: Path) -> Settings:
    try:
        return Settings.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
    except FileNotFoundError:
        return Settings()
    except (ValueError, ValidationError) as e:
        log.warning("settings file unreadable, using defaults: %s", e)
        return Settings()


def save_settings(path: Path, s: Settings) -> None:
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(s.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
