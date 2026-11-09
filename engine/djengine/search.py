import logging
import re
from typing import Callable, Literal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel

log = logging.getLogger(__name__)

Kind = Literal["song", "video", "playlist", "soundcloud"]
SearchKind = Literal["songs", "videos", "playlists", "soundcloud"]
SC_RESULTS = 25
RADIO_LIMIT = 50
SC_PREVIEW_S = 31  # Go+ tracks only stream a 30 s preview
MAX_RESULTS = 30
PLAYLIST_LIMIT = 500
SONG_MIN_S, SONG_MAX_S = 60, 1200
VIDEO_MIN_S = 60


class SearchResult(BaseModel):
    kind: Kind
    id: str
    title: str
    artist: str
    album: str = ""
    duration_s: int | None
    views: int | None
    thumbnail: str | None
    url: str
    track_count: int | None = None
    in_library: bool = False
    source: Literal["youtube", "soundcloud"] = "youtube"
    preview_only: bool = False


class PlaylistInfo(BaseModel):
    id: str
    title: str
    tracks: list[SearchResult]


_SUFFIX = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def parse_views(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"(\d[\d,\.]*)\s*([KMB])?", str(text).upper())
    if not m:
        return None
    num, suffix = m.group(1), m.group(2)
    if suffix:
        return int(round(float(num.replace(",", "")) * _SUFFIX[suffix]))
    return int(num.replace(",", "").replace(".", ""))


def filter_results(items: list[SearchResult]) -> list[SearchResult]:
    out = []
    seen: set[str] = set()
    for it in items:
        if not it.title.strip() or not it.id or it.id in seen:  # YouTube Music repeats some videos
            continue
        if it.kind == "song" and (it.duration_s is None or not SONG_MIN_S <= it.duration_s <= SONG_MAX_S):
            continue
        if it.kind == "video" and (it.duration_s is None or it.duration_s < VIDEO_MIN_S):
            continue
        seen.add(it.id)
        out.append(it)
    return out


def resolve_url(text: str) -> tuple[Literal["song", "playlist"], str] | None:
    text = text.strip()
    if not re.match(r"^(https?://)?([\w-]+\.)*(youtube\.com|youtu\.be)/", text, re.I):
        return None
    u = urlparse(text if "://" in text else "https://" + text)
    qs = parse_qs(u.query)
    if u.netloc.lower().endswith("youtu.be"):
        vid = u.path.strip("/").split("/")[0]
        return ("song", vid) if vid else None
    if u.path.startswith("/shorts/"):
        return "song", u.path.split("/")[2]
    if "v" in qs:
        return "song", qs["v"][0]
    if "list" in qs:
        return "playlist", qs["list"][0]
    return None


def _length_s(text: str) -> int | None:
    try:
        parts = [int(p) for p in text.split(":")]
    except ValueError:
        return None
    s = 0
    for p in parts:
        s = s * 60 + p
    return s


def _thumb(item: dict) -> str | None:
    thumbs = item.get("thumbnails") or []
    return thumbs[-1]["url"] if thumbs else None


def _artists(item: dict) -> str:
    names = [a.get("name", "") for a in item.get("artists") or [] if a.get("name")]
    return ", ".join(names) or item.get("author") or ""


def _from_ytm(item: dict, kind: Kind) -> SearchResult:
    if kind == "playlist":
        pid = (item.get("browseId") or item.get("playlistId") or "").removeprefix("VL")
        count = item.get("itemCount")
        return SearchResult(
            kind="playlist", id=pid, title=item.get("title") or "", artist=item.get("author") or "",
            duration_s=None, views=None, thumbnail=_thumb(item),
            url=f"https://music.youtube.com/playlist?list={pid}",
            track_count=int(count) if str(count or "").isdigit() else None,
        )
    vid = item.get("videoId") or ""
    album = item.get("album") or {}
    return SearchResult(
        kind=kind, id=vid, title=item.get("title") or "", artist=_artists(item),
        album=album.get("name", "") if isinstance(album, dict) else "",
        duration_s=item.get("duration_seconds"), views=parse_views(item.get("views")),
        thumbnail=_thumb(item), url=f"https://music.youtube.com/watch?v={vid}",
    )


def _from_flat(entry: dict) -> SearchResult:
    vid = entry.get("id") or ""
    thumbs = entry.get("thumbnails") or []
    return SearchResult(
        kind="video", id=vid, title=entry.get("title") or "",
        artist=entry.get("channel") or entry.get("uploader") or "",
        duration_s=int(entry["duration"]) if entry.get("duration") else None,
        views=entry.get("view_count"), thumbnail=thumbs[-1]["url"] if thumbs else None,
        url=f"https://www.youtube.com/watch?v={vid}",
    )


def soundcloud_results(entries: list[dict]) -> list[SearchResult]:
    """yt-dlp flat SoundCloud entries → results; Go+ previews stay (marked) so the user sees why they cannot download."""
    out = []
    for e in entries:
        if not e.get("id") or not (e.get("title") or "").strip():
            continue
        dur = float(e["duration"]) if e.get("duration") else None
        preview = e.get("availability") == "premium_only" or (dur is not None and 29 <= dur <= SC_PREVIEW_S)
        if not preview and (dur is None or dur < SONG_MIN_S):
            continue
        thumbs = e.get("thumbnails") or []
        out.append(SearchResult(
            kind="soundcloud", id=f"sc:{e['id']}", title=e["title"], artist=e.get("uploader") or "",
            duration_s=round(dur) if dur else None, views=e.get("view_count"),
            thumbnail=thumbs[-1]["url"] if thumbs else None, url=e.get("webpage_url") or e.get("url") or "",
            source="soundcloud", preview_only=preview,
        ))
    return out


def _sc_flat(q: str) -> list[dict]:
    import yt_dlp

    with yt_dlp.YoutubeDL({"extract_flat": True, "quiet": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(q, download=False)
    return info.get("entries") or []


def _ytdlp_flat_search(q: str) -> list[dict]:
    import yt_dlp

    with yt_dlp.YoutubeDL({"extract_flat": True, "quiet": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(f"ytsearch{MAX_RESULTS}:{q}", download=False)
    return info.get("entries") or []


class SearchService:
    def __init__(self, ytm=None, fallback: Callable[[str], list[dict]] | None = None,
                 sc_fetch: Callable[[str], list[dict]] | None = None):
        self._ytm = ytm
        self._fallback = fallback or _ytdlp_flat_search
        self._sc_fetch = sc_fetch or _sc_flat

    def read_link(self, text: str):
        from .discover.links import BAD_LINK, parse_link, read_link
        from .errors import UserError

        link = parse_link(text)
        if link is None:
            raise UserError(*BAD_LINK)
        return read_link(link)

    def soundcloud(self, q: str) -> list[SearchResult]:
        return soundcloud_results(self._sc_fetch(f"scsearch{SC_RESULTS}:{q}"))

    @property
    def ytm(self):
        if self._ytm is None:
            from ytmusicapi import YTMusic

            self._ytm = YTMusic()
        return self._ytm

    def search(self, q: str, kind: SearchKind) -> list[SearchResult]:
        if kind == "soundcloud":
            return self.soundcloud(q)
        resolved = resolve_url(q)
        if resolved:
            rkind, rid = resolved
            if rkind == "playlist":
                pl = self.get_playlist(rid)
                return [SearchResult(
                    kind="playlist", id=pl.id, title=pl.title, artist="", duration_s=None, views=None,
                    thumbnail=pl.tracks[0].thumbnail if pl.tracks else None,
                    url=f"https://music.youtube.com/playlist?list={pl.id}", track_count=len(pl.tracks),
                )]
            return [self.get_song(rid)]
        single = kind[:-1]  # songs -> song
        try:
            raw = self.ytm.search(q, filter=kind, limit=MAX_RESULTS)
            items = [_from_ytm(i, single) for i in raw]
        except Exception as e:
            log.warning("ytmusicapi search failed, using yt-dlp fallback: %s", e)
            items = [_from_flat(e) for e in self._fallback(q)]
            if kind == "songs":
                items = [i for i in items if i.duration_s and SONG_MIN_S <= i.duration_s <= SONG_MAX_S]
        if single == "playlist":
            return [i for i in items if i.id and i.title.strip()][:MAX_RESULTS]
        return filter_results(items)[:MAX_RESULTS]

    def similar(self, video_id: str) -> list[SearchResult]:
        """YouTube Music radio of a song, without the song itself."""
        w = self.ytm.get_watch_playlist(videoId=video_id, radio=True, limit=RADIO_LIMIT)
        items = []
        for t in w.get("tracks") or []:
            if not t.get("videoId") or t["videoId"] == video_id:
                continue
            r = _from_ytm(t, "song")
            if r.duration_s is None and t.get("length"):
                r.duration_s = _length_s(t["length"])
            items.append(r)
        return filter_results(items)

    def moods(self) -> list[dict]:
        cats = self.ytm.get_mood_categories()
        return [{"title": title, "items": [{"title": i["title"], "params": i["params"]} for i in items]}
                for title, items in cats.items()]

    def mood_playlists(self, params: str) -> list[SearchResult]:
        return [r for r in (_from_ytm(p, "playlist") for p in self.ytm.get_mood_playlists(params)) if r.id]

    def get_song(self, video_id: str) -> SearchResult:
        d = self.ytm.get_song(video_id)["videoDetails"]
        thumbs = (d.get("thumbnail") or {}).get("thumbnails") or []
        return SearchResult(
            kind="song", id=d.get("videoId", video_id), title=d.get("title", ""), artist=d.get("author", ""),
            duration_s=int(d["lengthSeconds"]) if d.get("lengthSeconds") else None,
            views=int(d["viewCount"]) if str(d.get("viewCount", "")).isdigit() else None,
            thumbnail=thumbs[-1]["url"] if thumbs else None,
            url=f"https://music.youtube.com/watch?v={video_id}",
        )

    def get_playlist(self, playlist_id: str) -> PlaylistInfo:
        pl = self.ytm.get_playlist(playlist_id, limit=PLAYLIST_LIMIT)
        tracks = [_from_ytm(t, "song") for t in pl.get("tracks") or [] if t.get("videoId")]
        tracks = [t for t in tracks if t.title.strip()]
        return PlaylistInfo(id=pl.get("id") or playlist_id, title=pl.get("title") or "Playlist", tracks=tracks)
