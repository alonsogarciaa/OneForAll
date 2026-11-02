from pathlib import Path

from ..naming import render_name

STEMS = ("vocals", "drums", "bass", "guitar", "piano", "other")
KARAOKE = ("lead_vocals", "backing_vocals")
LABELS_ES = {
    "vocals": "Voz", "drums": "Batería", "bass": "Bajo", "guitar": "Guitarra", "piano": "Piano", "other": "Resto",
    "lead_vocals": "Voz principal", "backing_vocals": "Coros",
}
_EXT = {"wav16": "wav", "wav24": "wav", "flac": "flac", "mp3": "mp3"}


def ext_for(fmt: str) -> str:
    return _EXT[fmt]


def stems_root(settings) -> Path:
    return Path(settings.stems_dir) if settings.stems_dir else Path(settings.music_dir) / "Stems"


def stems_folder(settings, meta: dict) -> Path:
    """<stems_dir>/<Artist - Title>/ (same naming rules as downloads)."""
    return stems_root(settings) / render_name(settings.name_template, meta)
