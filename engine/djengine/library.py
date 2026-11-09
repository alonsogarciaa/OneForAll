import re
import sqlite3
import threading
import unicodedata
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT UNIQUE,
    title TEXT NOT NULL,
    artist TEXT NOT NULL DEFAULT '',
    album TEXT NOT NULL DEFAULT '',
    duration_s INTEGER,
    views INTEGER,
    path TEXT NOT NULL,
    format TEXT NOT NULL DEFAULT '',
    bitrate INTEGER,
    cover_path TEXT,
    added_at TEXT NOT NULL,
    bpm REAL,
    musical_key TEXT,
    camelot TEXT,
    norm_key TEXT,
    missing INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tracks_norm ON tracks(norm_key);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    video_id TEXT,
    title TEXT NOT NULL DEFAULT '',
    artist TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yt_id TEXT,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL,
    track_id INTEGER NOT NULL,
    position INTEGER NOT NULL
);
"""

_NOISE_BRACKETS = re.compile(
    r"[\(\[][^\)\]]*\b(official|video|audio|lyrics?|letra|visuali[sz]er|hd|4k)\b[^\)\]]*[\)\]]", re.I
)
_FEAT = re.compile(r"\s*[\(\[]?\b(ft\.?|feat\.?|featuring)\s.*$", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_key(artist: str, title: str) -> str:
    def clean(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "")
        s = "".join(c for c in s if not unicodedata.combining(c)).lower()
        s = _NOISE_BRACKETS.sub(" ", s)
        s = _FEAT.sub("", s)
        return re.sub(r"[^a-z0-9]+", " ", s).strip()

    return f"{clean(artist)}|{clean(title)}"


@dataclass
class TrackRecord:
    id: int | None
    video_id: str | None
    title: str
    artist: str
    album: str
    duration_s: int | None
    views: int | None
    path: str
    format: str
    bitrate: int | None
    cover_path: str | None
    added_at: str
    bpm: float | None = None
    musical_key: str | None = None
    camelot: str | None = None
    missing: bool = False
    lufs: float | None = None
    analyzed_at: str | None = None


@dataclass
class HistoryEntry:
    id: int
    track_id: int | None
    video_id: str | None
    title: str
    artist: str
    action: str
    status: str
    at: str


_TRACK_COLS = [f.name for f in fields(TrackRecord)]


class Library:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            cols = {r[1] for r in self._conn.execute("PRAGMA table_info(tracks)")}
            for col, decl in (("lufs", "REAL"), ("analyzed_at", "TEXT")):  # phase 2 migration
                if col not in cols:
                    self._conn.execute(f"ALTER TABLE tracks ADD COLUMN {col} {decl}")
            self._conn.commit()

    def _exec(self, sql: str, params=()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _query(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    @staticmethod
    def _to_track(r: sqlite3.Row) -> TrackRecord:
        d = {k: r[k] for k in _TRACK_COLS}
        d["missing"] = bool(d["missing"])
        return TrackRecord(**d)

    def add_track(self, rec: TrackRecord) -> int:
        d = asdict(rec)
        d.pop("id")
        d["added_at"] = d["added_at"] or _now()
        d["missing"] = int(d["missing"])
        d["norm_key"] = normalize_key(rec.artist, rec.title)
        cols = ", ".join(d)
        marks = ", ".join("?" for _ in d)
        # Same video downloaded again with "Descargar igualmente": keep one row per video, pointing at the newest file.
        sql = f"INSERT INTO tracks ({cols}) VALUES ({marks}) ON CONFLICT(video_id) DO UPDATE SET " + ", ".join(
            f"{k}=excluded.{k}" for k in d if k != "video_id"
        )
        cur = self._exec(sql, tuple(d.values()))
        if rec.video_id:
            return self._query("SELECT id FROM tracks WHERE video_id=?", (rec.video_id,))[0]["id"]
        return cur.lastrowid

    def find_duplicate(self, video_id: str | None, artist: str, title: str) -> TrackRecord | None:
        """Only tracks whose file still exists count: a deleted file should be downloadable again."""
        candidates: list[sqlite3.Row] = []
        if video_id:
            candidates += self._query("SELECT * FROM tracks WHERE video_id=?", (video_id,))
        if title:
            candidates += self._query("SELECT * FROM tracks WHERE norm_key=? ORDER BY id DESC", (normalize_key(artist, title),))
        for r in candidates:
            if Path(r["path"]).exists():
                return self._to_track(r)
        return None

    def list_tracks(self, q: str = "") -> list[TrackRecord]:
        like = f"%{q}%"
        rows = self._query(
            "SELECT * FROM tracks WHERE title LIKE ? OR artist LIKE ? OR album LIKE ? ORDER BY id DESC",
            (like, like, like),
        )
        return [self._to_track(r) for r in rows]

    def refresh_missing(self) -> int:
        rows = self._query("SELECT id, path FROM tracks")
        missing = [r["id"] for r in rows if not Path(r["path"]).exists()]
        present = [r["id"] for r in rows if r["id"] not in set(missing)]
        with self._lock:
            self._conn.executemany("UPDATE tracks SET missing=1 WHERE id=?", [(i,) for i in missing])
            self._conn.executemany("UPDATE tracks SET missing=0 WHERE id=?", [(i,) for i in present])
            self._conn.commit()
        return len(missing)

    def track_by_path(self, path: str) -> TrackRecord | None:
        rows = self._query("SELECT * FROM tracks WHERE path=?", (str(path),))
        return self._to_track(rows[0]) if rows else None

    def set_track_analysis(self, path: str, bpm: float | None, musical_key: str, camelot: str, lufs: float | None) -> bool:
        cur = self._exec(
            "UPDATE tracks SET bpm=?, musical_key=?, camelot=?, lufs=?, analyzed_at=? WHERE path=?",
            (bpm, musical_key, camelot, lufs, _now(), str(path)),
        )
        return cur.rowcount > 0

    def add_history(self, video_id, title, artist, action, status, track_id=None) -> int:
        cur = self._exec(
            "INSERT INTO history (track_id, video_id, title, artist, action, status, at) VALUES (?,?,?,?,?,?,?)",
            (track_id, video_id, title, artist, action, status, _now()),
        )
        return cur.lastrowid

    def list_history(self) -> list[HistoryEntry]:
        return [HistoryEntry(**dict(r)) for r in self._query("SELECT * FROM history ORDER BY id DESC")]

    def delete_history(self, ids: list[int] | None) -> int:
        if ids is None:
            return self._exec("DELETE FROM history").rowcount
        if not ids:
            return 0
        marks = ",".join("?" for _ in ids)
        return self._exec(f"DELETE FROM history WHERE id IN ({marks})", tuple(ids)).rowcount

    def add_playlist(self, yt_id, name, path) -> int:
        return self._exec(
            "INSERT INTO playlists (yt_id, name, path, added_at) VALUES (?,?,?,?)", (yt_id, name, str(path), _now())
        ).lastrowid

    def list_playlists(self) -> list[tuple[int, str]]:
        return [(r["id"], r["name"]) for r in self._query("SELECT id, name FROM playlists ORDER BY id")]

    def playlist_track_ids(self, playlist_id: int) -> list[int]:
        rows = self._query("SELECT track_id FROM playlist_tracks WHERE playlist_id=? ORDER BY position", (playlist_id,))
        return [r["track_id"] for r in rows]

    def add_playlist_track(self, playlist_id, track_id, position) -> None:
        self._exec(
            "INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?,?,?)",
            (playlist_id, track_id, position),
        )
