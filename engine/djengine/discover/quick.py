"""Quick analysis of recommendations: BPM and key from a 60 s clip, cached for good by YouTube video id."""
import asyncio
import contextlib
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from ..errors import JobCancelled, UserError

log = logging.getLogger(__name__)
CLIP_S = 60.0
START_AT = 0.3
CONCURRENCY = 4  # 6-core CPU: 4 clips at once reach 80 % of 25 rows in under a minute
RETRY_AFTER = timedelta(hours=24)

_SCHEMA = """CREATE TABLE IF NOT EXISTS quick_analysis (
    video_id TEXT PRIMARY KEY, bpm REAL, tonic TEXT, mode TEXT, camelot TEXT, failed INTEGER NOT NULL, at TEXT NOT NULL)"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class QuickCache:
    def __init__(self, db_path: Path):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    def get(self, video_id: str) -> dict | None:
        with self._lock:
            r = self._conn.execute("SELECT bpm, camelot, failed, at FROM quick_analysis WHERE video_id=?",
                                   (video_id,)).fetchone()
        if r is None:
            return None
        bpm, camelot, failed, at = r
        if failed and _now() - datetime.fromisoformat(at) > RETRY_AFTER:
            return None  # failures are retried after a day (a video may come back, the network may have been down)
        return {"bpm": bpm, "camelot": camelot, "failed": bool(failed)}

    def put(self, video_id: str, result: dict | None) -> None:
        r = result or {}
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO quick_analysis VALUES (?,?,?,?,?,?,?)",
                               (video_id, r.get("bpm"), r.get("tonic"), r.get("mode"), r.get("camelot"),
                                0 if result else 1, _now().isoformat()))
            self._conn.commit()


def _cache(svc) -> QuickCache:
    c = getattr(svc, "_quick_cache", None)
    if c is None:
        c = QuickCache(svc.paths.db_path)
        object.__setattr__(svc, "_quick_cache", c)
    return c


def _from_library(svc, video_id: str) -> dict | None:
    track = svc.library.track_by_video_id(video_id)
    rec = svc.analysis.get(Path(track.path)) if track and svc.analysis is not None else None
    return {"bpm": rec.bpm, "camelot": rec.camelot, "failed": False} if rec and rec.bpm else None


def lookup(svc, video_ids: list[str]) -> dict[str, dict]:
    out = {}
    for v in video_ids:
        k = _from_library(svc, v) or _cache(svc).get(v)
        if k is not None:
            out[v] = k
    return out


def quick_analyse(path: Path, lo: int, hi: int) -> dict:
    import librosa

    from ..analysis.audio_io import decode
    from ..analysis.config import DEFAULT_KEY_METHOD, DEFAULT_TEMPO_METHOD
    from ..analysis.key import estimate_key
    from ..analysis.tempo import estimate_tempo

    mono44 = decode(path, sr=44100, mono=True).astype(np.float32)
    if mono44.size < 44100 * 5:
        raise UserError("unreadable", "Fragmento demasiado corto")
    y = librosa.resample(mono44, orig_sr=44100, target_sr=22050)
    tempo = estimate_tempo(y, 22050, method=DEFAULT_TEMPO_METHOD, lo=lo, hi=hi)
    key = estimate_key(mono44, 44100, method=DEFAULT_KEY_METHOD)
    return {"bpm": round(float(tempo.bpm), 1) if tempo.bpm else None, "tonic": key.tonic, "mode": key.mode,
            "camelot": key.camelot}


async def download_clip(ctx, url: str, start_s: float, seconds: float = CLIP_S) -> Path:
    """Only the clip, with yt-dlp download sections; if that fails, the smallest audio stream cut with ffmpeg."""
    from ..download import map_ytdlp_error, ytdlp_cmd
    from ..tools import find_tool

    out = ctx.tmp_dir / f"clip-{abs(hash(url))}"
    end = start_s + seconds

    async def run(*args: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.DEVNULL,
                                                    stderr=asyncio.subprocess.PIPE)
        ctx.register_process(proc)
        _, err = await proc.communicate()
        ctx.check_cancelled()
        return proc.returncode, err.decode("utf-8", "replace")

    ffmpeg_dir = str(Path(find_tool("ffmpeg")).parent)
    rc, err = await run(*ytdlp_cmd(), "-f", "bestaudio", "--no-playlist", "--no-part", "--download-sections",
                        f"*{start_s:.0f}-{end:.0f}", "--force-keyframes-at-cuts", "--ffmpeg-location", ffmpeg_dir,
                        "-o", f"{out}.%(ext)s", url)
    got = [p for p in ctx.tmp_dir.glob(out.name + ".*") if p.is_file()]
    if rc == 0 and got:
        return got[0]
    log.info("clip download failed, trying the whole small stream: %s", err[-300:])
    rc, err = await run(*ytdlp_cmd(), "-f", "worstaudio", "--no-playlist", "--no-part", "-o", f"{out}-full.%(ext)s", url)
    full = [p for p in ctx.tmp_dir.glob(out.name + "-full.*") if p.is_file()]
    if rc != 0 or not full:
        raise map_ytdlp_error(err)
    cut = ctx.tmp_dir / f"{out.name}-cut.wav"
    rc, err = await run(find_tool("ffmpeg"), "-v", "error", "-nostdin", "-y", "-ss", f"{start_s:.2f}",
                        "-t", f"{seconds:.2f}", "-i", str(full[0]), str(cut))
    if rc != 0:
        raise UserError("unreadable", "No se pudo leer el fragmento")
    return cut


def make_quick_runner(svc, video_ids: list[str], durations: list[int | None]):
    async def run(ctx) -> dict:
        ids = list(dict.fromkeys(video_ids))
        dur = dict(zip(video_ids, durations))
        cache = _cache(svc)
        sem = asyncio.Semaphore(CONCURRENCY)
        lo, hi = svc.settings.bpm_min, svc.settings.bpm_max
        done = 0

        async def emit(v: str, r: dict) -> None:
            await svc.hub.broadcast({"type": "quick.result", "video_id": v, "bpm": r.get("bpm"),
                                     "camelot": r.get("camelot"), "failed": bool(r.get("failed"))})

        async def one(v: str) -> None:
            nonlocal done
            known = _from_library(svc, v) or cache.get(v)
            if known is None:
                async with sem:
                    ctx.check_cancelled()
                    url = f"https://music.youtube.com/watch?v={v}"
                    start = (dur.get(v) or 200) * START_AT
                    try:
                        clip = await svc.clip_downloader(ctx, url, start, CLIP_S)
                        r = await asyncio.to_thread(quick_analyse, clip, lo, hi)
                        with contextlib.suppress(OSError):
                            clip.unlink()
                    except (JobCancelled, asyncio.CancelledError):
                        raise
                    except Exception as e:  # one bad video never stops the others
                        log.info("quick analysis failed for %s: %s", v, e)
                        r = None
                    cache.put(v, r)
                    known = cache.get(v) or {"bpm": None, "camelot": None, "failed": True}
            done += 1
            ctx.report("analysing", 100 * done / max(1, len(ids)))
            await emit(v, known)

        await asyncio.gather(*(one(v) for v in ids))
        return {"count": len(ids)}

    return run
