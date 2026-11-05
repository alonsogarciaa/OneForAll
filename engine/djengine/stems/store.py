import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from ..analysis.store import file_stamp

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stems (
    path TEXT NOT NULL,
    stem TEXT NOT NULL,
    file TEXT NOT NULL,
    model TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (path, stem)
);
"""


def _norm(p) -> str:
    return os.path.normcase(os.path.realpath(str(p)))


def key(p) -> str:
    """Stable identity of a path on this machine (case-insensitive on Windows)."""
    return os.path.normcase(os.path.abspath(str(p)))


class StemsStore:
    """Which stem files exist for which source file; rows go stale when the source or the stem changes."""

    def __init__(self, db_path: Path):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._lock:
            self._conn.executescript(_SCHEMA)
            cols = {r[1] for r in self._conn.execute("PRAGMA table_info(stems)")}
            if "file_key" not in cols:
                self._conn.execute("ALTER TABLE stems ADD COLUMN file_key TEXT")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_stems_file_key ON stems(file_key)")
            self._conn.commit()

    def _rows(self, path) -> list[tuple]:
        with self._lock:
            return self._conn.execute("SELECT stem, file, size, mtime FROM stems WHERE path=?", (key(path),)).fetchall()

    def _delete(self, path, stem=None) -> None:
        with self._lock:
            if stem is None:
                self._conn.execute("DELETE FROM stems WHERE path=?", (key(path),))
            else:
                self._conn.execute("DELETE FROM stems WHERE path=? AND stem=?", (key(path), stem))
            self._conn.commit()

    def get(self, path) -> dict[str, Path]:
        rows = self._rows(path)
        if not rows:
            return {}
        try:
            size, mtime = file_stamp(path)
        except OSError:
            self._delete(path)
            return {}
        if any(r[2] != size or abs(r[3] - mtime) > 1e-3 for r in rows):
            self._delete(path)  # source edited since: stems no longer match it
            return {}
        out = {}
        for stem, file, _, _ in rows:
            if Path(file).is_file():
                out[stem] = Path(file)
            else:
                self._delete(path, stem)
        return out

    def add(self, path, stem: str, file: Path, model: str) -> None:
        size, mtime = file_stamp(path)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO stems (path, stem, file, model, size, mtime, created_at, file_key) VALUES (?,?,?,?,?,?,?,?)",
                (key(path), stem, str(Path(file)), model, size, mtime, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 key(file)),
            )
            self._conn.commit()

    def folder_for(self, path) -> Path | None:
        files = list(self.get(path).values())
        return files[0].parent if files else None

    def is_stem_file(self, file) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT path FROM stems WHERE file_key=?", (key(file),)).fetchone()
        return bool(row) and any(key(f) == key(file) for f in self.get(row[0]).values())

    def restamp(self, path, before: tuple[int, float]) -> None:
        """After we rewrote the source's tags ourselves: keep rows that matched the old stamp valid."""
        size, mtime = file_stamp(path)
        with self._lock:
            self._conn.execute(
                "UPDATE stems SET size=?, mtime=? WHERE path=? AND size=? AND abs(mtime - ?) < 0.001",
                (size, mtime, key(path), before[0], before[1]),
            )
            self._conn.commit()

    def sources_in_folder(self, folder) -> set[str]:
        """Source files that own stems stored in this folder."""
        target = key(folder)
        with self._lock:
            rows = self._conn.execute("SELECT path, file FROM stems").fetchall()
        return {src for src, f in rows if key(Path(f).parent) == target}

    def sources_with_stems(self) -> set[str]:
        with self._lock:
            return {r[0] for r in self._conn.execute("SELECT DISTINCT path FROM stems")}
