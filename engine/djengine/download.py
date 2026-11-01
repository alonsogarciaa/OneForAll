import asyncio
import logging
import os
import re
import shlex
import sys
import urllib.request
from pathlib import Path

from .errors import UserError, user_error
from .tools import find_tool

log = logging.getLogger(__name__)

_PROGRESS = re.compile(
    r"^\[download\]\s+(?P<pct>\d+(?:\.\d+)?)%(?:.*?\bat\s+(?P<speed>\S+))?(?:.*?\bETA\s+(?P<eta>\S+))?"
)
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("unavailable", re.compile(r"Private video|Video unavailable|has been removed|This video is not available", re.I)),
    ("blocked", re.compile(r"Sign in to confirm your age|age[- ]restricted|available in your country|\bgeo", re.I)),
    ("offline", re.compile(r"getaddrinfo|Network is unreachable|timed out|Temporary failure in name resolution|Failed to resolve", re.I)),
    ("disk", re.compile(r"No space left|Permission denied|Errno 28|Errno 13", re.I)),
]


def parse_progress(line: str) -> tuple[float, str | None, str | None] | None:
    m = _PROGRESS.match(line.strip())
    if not m:
        return None
    return float(m["pct"]), m["speed"], m["eta"]


def map_ytdlp_error(stderr: str) -> UserError:
    for code, pat in _PATTERNS:
        if pat.search(stderr):
            return user_error(code)
    return user_error("extractor_outdated")


def ytdlp_cmd() -> list[str]:
    override = os.environ.get("ONEFORALL_YTDLP")
    if override:
        return [p.strip('"') for p in shlex.split(override, posix=False)]
    try:
        return [find_tool("yt-dlp")]
    except UserError:
        return [sys.executable, "-m", "yt_dlp"]


async def download_audio(ctx, url: str) -> Path:
    out_tpl = str(ctx.tmp_dir / "src.%(ext)s")
    proc = await asyncio.create_subprocess_exec(
        *ytdlp_cmd(), "-f", "bestaudio", "--no-playlist", "--newline", "--no-part", "--no-mtime",
        "-o", out_tpl, url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    ctx.register_process(proc)
    ctx.report("downloading", 0)
    stderr_task = asyncio.create_task(proc.stderr.read())
    async for raw in proc.stdout:
        parsed = parse_progress(raw.decode("utf-8", "replace"))
        if parsed:
            pct, speed, eta = parsed
            ctx.report("downloading", pct, speed, eta)
    await proc.wait()
    stderr = (await stderr_task).decode("utf-8", "replace")
    ctx.check_cancelled()
    if proc.returncode != 0:
        log.warning("yt-dlp failed (%s) for %s: %s", proc.returncode, url, stderr[-2000:])
        raise map_ytdlp_error(stderr)
    files = [p for p in ctx.tmp_dir.glob("src.*") if p.is_file()]
    if len(files) != 1:
        log.warning("yt-dlp produced %d files for %s", len(files), url)
        raise user_error("extractor_outdated")
    return files[0]


def fetch_thumbnail(url: str | None) -> bytes | None:
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read()
    except Exception as e:
        log.info("thumbnail fetch failed for %s: %s", url, e)
        return None
