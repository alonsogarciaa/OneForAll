"""Links from Spotify, Apple Music and SoundCloud → a list of songs to find and download.

Spotify and Apple Music are read from their public pages (no account): the JSON each page embeds. When a service
changes its page the reader fails with a clear "source_changed" error instead of importing nothing.
"""
import json
import logging
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Literal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel

from ..errors import UserError

log = logging.getLogger(__name__)
Service = Literal["spotify", "apple", "soundcloud"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
SPOTIFY_LIMIT = 100
BAD_LINK = ("bad_link", "No se pudo leer el enlace")
_NAMES = {"spotify": "Spotify", "apple": "Apple Music"}
_SC_RESERVED = {"tracks", "albums", "likes", "reposts", "followers", "following", "popular-tracks", "comments", "sets"}


class ImportItem(BaseModel):
    title: str
    artist: str
    duration_s: int | None = None
    url: str | None = None  # SoundCloud only: already downloadable, no matching needed
    id: str | None = None  # SoundCloud only: "sc:<id>", the library's video_id


class ImportList(BaseModel):
    name: str
    service: Service
    items: list[ImportItem]
    truncated: bool = False


@dataclass
class Link:
    service: Service
    kind: Literal["track", "album", "playlist"]
    id: str
    url: str


def _final_url(url: str) -> str:
    """Follow redirects of a short link (spotify.link, on.soundcloud.com)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.geturl()


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def parse_link(text: str) -> Link | None:
    text = text.strip()
    m = re.fullmatch(r"spotify:(track|album|playlist):([A-Za-z0-9]+)", text)
    if m:
        return Link("spotify", m[1], m[2], f"https://open.spotify.com/{m[1]}/{m[2]}")
    if not re.match(r"^(https?://)?[\w.-]+\.[a-z]{2,}/", text, re.I):
        return None
    u = urlparse(text if "://" in text else "https://" + text)
    host = u.netloc.lower().removeprefix("www.").removeprefix("m.")
    parts = [p for p in u.path.split("/") if p]
    if host in ("spotify.link", "on.soundcloud.com"):
        try:
            final = _final_url(text if "://" in text else "https://" + text)
        except (OSError, ValueError):
            return None
        return parse_link(final) if final != text else None
    if host == "open.spotify.com":
        if parts and parts[0].startswith("intl-"):
            parts = parts[1:]
        if len(parts) >= 2 and parts[0] in ("track", "album", "playlist"):
            return Link("spotify", parts[0], parts[1], f"https://open.spotify.com/{parts[0]}/{parts[1]}")
        return None
    if host == "music.apple.com":
        if len(parts) >= 3 and parts[1] in ("album", "playlist", "song"):
            track = parse_qs(u.query).get("i")
            if parts[1] == "album" and track:
                return Link("apple", "track", track[0], text)
            kind = "track" if parts[1] == "song" else parts[1]
            return Link("apple", kind, parts[-1], text)
        return None
    if host == "soundcloud.com":
        clean = f"https://soundcloud.com/{'/'.join(parts)}"
        if len(parts) == 3 and parts[1] == "sets":
            return Link("soundcloud", "playlist", "/".join(parts), clean)
        if len(parts) == 2 and parts[1] not in _SC_RESERVED:
            return Link("soundcloud", "track", "/".join(parts), clean)
    return None


def _changed(service: str) -> UserError:
    return UserError("source_changed", f"{_NAMES[service]} ha cambiado; actualiza la app")


def _fetch(fetch: Callable[[str], str], url: str) -> str:
    try:
        return fetch(url)
    except (urllib.error.URLError, OSError, ValueError) as e:
        log.info("link fetch failed for %s: %s", url, e)
        raise UserError(*BAD_LINK)


def _script_json(html: str, script_id: str):
    m = re.search(rf'<script[^>]*id="{script_id}"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def _secs(ms) -> int | None:
    try:
        return round(float(ms) / 1000) or None
    except (TypeError, ValueError):
        return None


def read_spotify(link: Link, fetch: Callable[[str], str] = _get) -> ImportList:
    html = _fetch(fetch, f"https://open.spotify.com/embed/{link.kind}/{link.id}")
    try:
        entity = _script_json(html, "__NEXT_DATA__")["props"]["pageProps"]["state"]["data"]["entity"]
        if link.kind == "track":
            artists = ", ".join(a["name"] for a in entity.get("artists") or []) or entity.get("subtitle") or ""
            items = [ImportItem(title=entity["title"] or entity["name"], artist=artists, duration_s=_secs(entity.get("duration")))]
        else:
            items = [ImportItem(title=t["title"], artist=t.get("subtitle") or "", duration_s=_secs(t.get("duration")))
                     for t in entity["trackList"]]
        name = entity.get("name") or entity.get("title") or "Spotify"
    except (TypeError, KeyError, ValueError) as e:
        log.warning("spotify page structure changed: %s", e)
        raise _changed("spotify")
    return ImportList(name=name, service="spotify", items=items, truncated=len(items) >= SPOTIFY_LIMIT)


def read_apple(link: Link, fetch: Callable[[str], str] = _get) -> ImportList:
    html = _fetch(fetch, link.url)
    try:
        sections = _script_json(html, "serialized-server-data")["data"][0]["data"]["sections"]
        header = next((s["items"][0] for s in sections if "header" in s.get("id", "") and s.get("items")), {})
        rows = next(s["items"] for s in sections if s.get("itemKind") in ("trackLockup", "listLockup") and s.get("items"))
        items = [ImportItem(title=r["title"], artist=r.get("artistName") or "", duration_s=_secs(r.get("duration")))
                 for r in rows if r.get("title")]
        if not items:
            raise KeyError("no tracks")
        name = header.get("title") or "Apple Music"
        total = header.get("trackCount")
    except (TypeError, KeyError, ValueError, IndexError, StopIteration) as e:
        log.warning("apple music page structure changed: %s", e)
        raise _changed("apple")
    return ImportList(name=name, service="apple", items=items, truncated=bool(total and total > len(items)))


def _ytdlp_json(url: str) -> dict:
    from ..download import ytdlp_cmd

    r = subprocess.run([*ytdlp_cmd(), "--flat-playlist", "-J", url], capture_output=True, text=True, encoding="utf-8", timeout=120)
    if r.returncode != 0:
        log.info("yt-dlp could not read %s: %s", url, r.stderr[-500:])
        raise UserError(*BAD_LINK)
    return json.loads(r.stdout)


def read_soundcloud(link: Link, run: Callable[[str], dict] = _ytdlp_json) -> ImportList:
    data = run(link.url)
    entries = data.get("entries") if data.get("_type") == "playlist" else [data]
    items = []
    for e in entries or []:
        url = e.get("webpage_url") or e.get("url")
        if not url:
            continue
        items.append(ImportItem(title=e.get("title") or "", artist=e.get("uploader") or "",
                                duration_s=round(e["duration"]) if e.get("duration") else None, url=url,
                                id=f"sc:{e['id']}" if e.get("id") else None))
    if not items:
        raise UserError(*BAD_LINK)
    return ImportList(name=data.get("title") or "SoundCloud", service="soundcloud", items=items)


def read_link(link: Link) -> ImportList:
    if link.service == "spotify":
        return read_spotify(link)
    if link.service == "apple":
        return read_apple(link)
    return read_soundcloud(link)
