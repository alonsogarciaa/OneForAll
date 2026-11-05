import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from ..stems.names import KARAOKE, STEMS
from ..stems.store import key

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mixer_state (
    path_key TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class StemState(BaseModel):
    gain: float = Field(default=1.0, ge=0, le=1.5)
    mute: bool = False
    solo: bool = False
    semis: int = Field(default=0, ge=-12, le=12)


class Loop(BaseModel):
    start: float = Field(ge=0)
    end: float

    @model_validator(mode="after")
    def _ordered(self):
        if self.end <= self.start:
            raise ValueError("el bucle debe terminar después de empezar")
        return self


class Metronome(BaseModel):
    on: bool = False
    volume: float = Field(default=0.6, ge=0, le=1)
    count_in: Literal[0, 1, 2] = 1
    meter: Literal["2/4", "3/4", "4/4", "6/8"] = "4/4"
    offset: int = Field(default=0, ge=-7, le=7)


class MixState(BaseModel):
    version: Literal[1] = 1
    rate: float = Field(default=1.0, ge=0.5, le=1.0)
    semis: int = Field(default=0, ge=-12, le=12)
    master: float = Field(default=1.0, ge=0, le=1.5)
    stems: dict[str, StemState] = Field(default_factory=dict)
    loop: Loop | None = None
    loop_on: bool = False
    metronome: Metronome = Field(default_factory=Metronome)

    @field_validator("stems")
    @classmethod
    def _known(cls, v):
        bad = [s for s in v if s not in STEMS + KARAOKE]
        if bad:
            raise ValueError(f"stem desconocido: {bad[0]}")
        return v


def effective_semis(state: MixState, stem: str) -> int:
    own = state.stems.get(stem, StemState()).semis
    return max(-12, min(12, state.semis + own))


def audible(state: MixState, names: list[str]) -> list[str]:
    """Solo wins: if any stem is solo only those sound; otherwise every non-muted stem."""
    st = {n: state.stems.get(n, StemState()) for n in names}
    if any(s.solo for s in st.values()):
        return [n for n in names if st[n].solo]
    return [n for n in names if not st[n].mute]


class MixerStore:
    """Last mixer settings per track (restored when the mixer reopens)."""

    def __init__(self, db_path: Path):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def get(self, path) -> MixState | None:
        with self._lock:
            row = self._conn.execute("SELECT state_json FROM mixer_state WHERE path_key=?", (key(path),)).fetchone()
        if not row:
            return None
        try:
            return MixState.model_validate(json.loads(row[0]))
        except (ValueError, ValidationError):  # older or damaged state: start from defaults
            return None

    def put(self, path, state: MixState) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO mixer_state (path_key, state_json, updated_at) VALUES (?,?,?)",
                (key(path), state.model_dump_json(), datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            self._conn.commit()
