import json
import logging
from pathlib import Path

from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

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
    analyze_on_download: bool = True
    key_notation: Literal["camelot", "musical"] = "camelot"
    bpm_min: int = Field(default=70, ge=40, le=250)
    bpm_max: int = Field(default=180, ge=40, le=250)
    stems_dir: str | None = None  # None: <music_dir>/Stems
    stems_format: Literal["wav16", "wav24", "flac", "mp3"] = "wav16"
    stems_backend: Literal["auto", "cpu"] = "auto"
    videos_dir: str | None = None  # None: <music_dir>/Videos
    enhance_on_download: bool = False
    enhance_mode: Literal["copy", "replace"] = "replace"
    enhance_format: Literal["same", "flac"] = "same"
    enhance_rtf: float | None = None  # measured seconds of compute per second of audio

    @model_validator(mode="after")
    def _bpm_range(self):
        if self.bpm_min >= self.bpm_max:
            raise ValueError("El mínimo debe ser menor que el máximo")
        return self


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
