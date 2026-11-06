import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    bpm REAL,
    bpm_confidence REAL,
    bpm_source TEXT NOT NULL DEFAULT 'auto',
    tonic TEXT,
    mode TEXT,
    camelot TEXT,
    key_confidence REAL,
    lufs REAL,
    peak_db REAL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""


@dataclass
class AnalysisRecord:
    path: str
    size: int
    mtime: float
    bpm: float | None
    bpm_confidence: float | None
    bpm_source: str
    tonic: str | None
    mode: str | None
    camelot: str | None
    key_confidence: float | None
    lufs: float | None
    peak_db: float | None
    version: int
    created_at: str


_COLS = [f.name for f in fields(AnalysisRecord)]


def file_stamp(path: Path) -> tuple[int, float]:
    st = Path(path).stat()
    return st.st_size, round(st.st_mtime, 3)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AnalysisStore:
    """Analysis cache for any file: one row per path, valid while size and mtime are unchanged."""

    def __init__(self, db_path: Path, sidecar_dir: Path):
        self.sidecar_dir = Path(sidecar_dir)
        self.sidecar_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def _sidecar_path(self, path: Path) -> Path:
        return self.sidecar_dir / (hashlib.sha1(str(Path(path)).encode("utf-8")).hexdigest() + ".json")

    def _row(self, path: Path):
        with self._lock:
            return self._conn.execute("SELECT * FROM analyses WHERE path=?", (str(Path(path)),)).fetchone()

    def get(self, path: Path) -> AnalysisRecord | None:
        r = self._row(path)
        if r is None:
            return None
        try:
            size, mtime = file_stamp(path)
        except OSError:
            return None
        if r["size"] != size or abs(r["mtime"] - mtime) > 1e-3:
            return None
        return AnalysisRecord(**{k: r[k] for k in _COLS})

    def get_any(self, path: Path) -> AnalysisRecord | None:
        """Row even if the file changed since (used to carry a manual BPM over)."""
        r = self._row(path)
        return AnalysisRecord(**{k: r[k] for k in _COLS}) if r else None

    def get_sidecar(self, path: Path) -> dict | None:
        p = self._sidecar_path(path)
        if not p.exists() or self.get(path) is None:
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def save(self, rec: AnalysisRecord, sidecar: dict) -> None:
        sp = self._sidecar_path(Path(rec.path))
        tmp = sp.with_suffix(".tmp")
        tmp.write_text(json.dumps(sidecar, allow_nan=False), encoding="utf-8")
        os.replace(tmp, sp)
        d = asdict(rec)
        marks = ",".join("?" for _ in d)
        with self._lock:
            self._conn.execute(f"INSERT OR REPLACE INTO analyses ({','.join(d)}) VALUES ({marks})", tuple(d.values()))
            self._conn.commit()

    def set_manual_bpm(self, path: Path, bpm: float) -> AnalysisRecord | None:
        return self.set_bpm(path, bpm, "manual")

    def set_bpm(self, path: Path, bpm: float | None, source: str) -> AnalysisRecord | None:
        with self._lock:
            self._conn.execute("UPDATE analyses SET bpm=?, bpm_source=? WHERE path=?",
                               (round(bpm, 1) if bpm else bpm, source, str(Path(path))))
            self._conn.commit()
        return self.get_any(path)

    def read_sidecar(self, path: Path) -> dict | None:
        """Sidecar even if the file changed since (to carry manual edits over a re-analysis)."""
        p = self._sidecar_path(Path(path))
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def _write_sidecar(self, path: Path, side: dict) -> None:
        sp = self._sidecar_path(Path(path))
        tmp = sp.with_suffix(".tmp")
        tmp.write_text(json.dumps(side, allow_nan=False), encoding="utf-8")
        os.replace(tmp, sp)

    def get_grid(self, path: Path):
        """Fixed grid of the analysis; version-1 sidecars are converted (anchor = first old beat)."""
        from ..prep.grid import Grid

        side = self.read_sidecar(path)
        rec = self.get_any(path)
        if side is None or rec is None:
            return None
        if side.get("grid"):
            return Grid.from_dict(side["grid"])
        old = side.get("beats") or []
        return Grid(float(old[0]) if old else 0.0, float(rec.bpm or 0))

    def save_grid(self, path: Path, grid) -> None:
        """Store the grid and rewrite the beat list from it (the waveform, mixer and metronome read the list)."""
        from ..prep.grid import beats

        side = self.read_sidecar(path)
        if side is None:
            return
        side["grid"] = grid.to_dict()
        side["beats"] = beats(grid, float(side.get("duration") or 0))
        self._write_sidecar(path, side)

    def get_sections(self, path: Path) -> list:
        from ..prep.sections import Section

        side = self.read_sidecar(path) or {}
        return [Section.from_dict(d) for d in side.get("sections") or []]

    def save_sections(self, path: Path, sections: list) -> None:
        side = self.read_sidecar(path)
        if side is None:
            return
        side["sections"] = [x.to_dict() for x in sections]
        self._write_sidecar(path, side)

    def restamp(self, path: Path) -> None:
        """Record the file's current size/mtime (after we rewrote its tags ourselves)."""
        size, mtime = file_stamp(path)
        with self._lock:
            self._conn.execute("UPDATE analyses SET size=?, mtime=? WHERE path=?", (size, mtime, str(Path(path))))
            self._conn.commit()

    def paths(self) -> set[str]:
        with self._lock:
            return {r[0] for r in self._conn.execute("SELECT path FROM analyses")}

    def delete(self, path: Path) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM analyses WHERE path=?", (str(Path(path)),))
            self._conn.commit()
        self._sidecar_path(path).unlink(missing_ok=True)
