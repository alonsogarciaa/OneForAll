"""Offline stand-ins used with `--fake` (E2E tests, UI work without YouTube)."""
import asyncio
import os
from pathlib import Path

from .errors import user_error
from .search import PlaylistInfo, SearchResult
from .tools import find_tool


def _song(i: int, title: str, artist: str = "Fake Artist", vid: str | None = None) -> SearchResult:
    vid = vid or f"fake{i}"
    return SearchResult(kind="song", id=vid, title=title, artist=artist, album="Fake Album", duration_s=5,
                        views=1000 * i, thumbnail=None, url=f"https://music.youtube.com/watch?v={vid}")


SONGS = [_song(1, "La Graciosa"), _song(2, "Otra Canción"), _song(3, "Tercera")]
VIDEO = SearchResult(kind="video", id="fakev1", title="Fake DJ Set", artist="Fake DJ", duration_s=5, views=50,
                     thumbnail=None, url="https://www.youtube.com/watch?v=fakev1")
PLAYLIST_TRACKS = [_song(10, "Playlist Uno"), _song(11, "Playlist Dos"), _song(12, "Private Song", vid="fakeprivate")]
PLAYLIST = SearchResult(kind="playlist", id="PLfake", title="Fake Playlist", artist="Fake Curator", duration_s=None,
                        views=None, thumbnail=None, url="https://music.youtube.com/playlist?list=PLfake",
                        track_count=len(PLAYLIST_TRACKS))


SC_TRACKS = [
    SearchResult(kind="soundcloud", id="sc:101", title="Fake SC Remix", artist="Fake SC", duration_s=200, views=10,
                 thumbnail=None, url="https://soundcloud.com/fake/remix", source="soundcloud"),
    SearchResult(kind="soundcloud", id="sc:102", title="Fake Go+ Track", artist="Fake SC", duration_s=30, views=10,
                 thumbnail=None, url="https://soundcloud.com/fake/goplus", source="soundcloud", preview_only=True),
]


def _rec(i: int, title: str) -> SearchResult:
    # ids ending in 8 analyse at 128 BPM in the fake clip downloader, the rest at 120
    vid = f"fakerec{i}"
    return SearchResult(kind="song", id=vid, title=title, artist="Fake Recs", album="", duration_s=200, views=100,
                        thumbnail=None, url=f"https://music.youtube.com/watch?v={vid}")


RECS = [_rec(i, f"Recomendada {i}") for i in range(1, 9)]


class FakeSearch:
    def search(self, q: str, kind: str) -> list[SearchResult]:
        return {"songs": list(SONGS), "videos": [VIDEO], "playlists": [PLAYLIST], "soundcloud": list(SC_TRACKS)}[kind]

    def soundcloud(self, q: str) -> list[SearchResult]:
        return list(SC_TRACKS)

    def read_link(self, text: str):
        from .discover.links import BAD_LINK, ImportItem, ImportList, parse_link

        link = parse_link(text)
        if link is None:
            from .errors import UserError

            raise UserError(*BAD_LINK)
        if link.service == "soundcloud":
            return ImportList(name="Fake SC Set", service="soundcloud", items=[
                ImportItem(title=t.title, artist=t.artist, duration_s=t.duration_s, url=t.url, id=t.id)
                for t in SC_TRACKS if not t.preview_only])
        return ImportList(name="Lista Fake", service=link.service, items=[
            ImportItem(title=s.title, artist=s.artist, duration_s=s.duration_s) for s in SONGS])

    def similar(self, video_id: str) -> list[SearchResult]:
        return [r for r in RECS if r.id != video_id]

    def moods(self) -> list[dict]:
        return [{"title": "Moods & moments", "items": [{"title": "Fiesta", "params": "fake-fiesta"}]},
                {"title": "Genres", "items": [{"title": "Reggaetón", "params": "fake-reggaeton"}]}]

    def mood_playlists(self, params: str) -> list[SearchResult]:
        return [PLAYLIST]

    def get_playlist(self, playlist_id: str) -> PlaylistInfo:
        return PlaylistInfo(id="PLfake", title="Fake Playlist", tracks=list(PLAYLIST_TRACKS))

    def get_song(self, video_id: str) -> SearchResult:
        return next((s for s in SONGS if s.id == video_id), SONGS[0])


async def fake_downloader(ctx, url: str) -> Path:
    """Generates a 5 s tone as the 'downloaded' file, spread over ONEFORALL_FAKE_DELAY seconds (default 2)."""
    delay = float(os.environ.get("ONEFORALL_FAKE_DELAY", "2"))
    steps = 10
    for i in range(1, steps + 1):
        await asyncio.sleep(delay / steps)
        ctx.check_cancelled()
        ctx.report("downloading", i * 100 / steps, "1.0MiB/s", "00:01")
    if "private" in url.lower():
        raise user_error("unavailable")
    out = ctx.tmp_dir / "src.wav"
    proc = await asyncio.create_subprocess_exec(
        find_tool("ffmpeg"), "-v", "error", "-nostdin", "-f", "lavfi", "-i", "sine=f=330:d=5", "-ac", "2", "-y", str(out),
    )
    ctx.register_process(proc)
    await proc.wait()
    ctx.check_cancelled()
    return out


async def fake_clip_downloader(ctx, url: str, start_s: float, seconds: float = 60) -> Path:
    """A 20 s click track standing in for the 60 s clip: 128 BPM when the id ends in 8, else 120."""
    import numpy as np
    import soundfile as sf

    if "private" in url.lower():
        raise user_error("unavailable")
    bpm = 128 if url.rstrip("/").endswith("8") else 120
    sr, n = 44100, int(0.02 * 44100)
    y = np.zeros(20 * sr, dtype=np.float32)
    click = (np.sin(2 * np.pi * 1000 * np.arange(n) / sr) * np.hanning(n)).astype(np.float32)
    t = 0.0
    while t < 19.9:
        i = int(t * sr)
        y[i:i + n] += click[: len(y) - i]
        t += 60.0 / bpm
    out = ctx.tmp_dir / f"clip-{abs(hash(url))}.wav"
    await asyncio.to_thread(sf.write, out, y, sr)
    return out


async def fake_video_downloader(ctx, url: str, quality: str) -> Path:
    """A 5 s test pattern standing in for the YouTube video; a "private" id is unavailable."""
    if "private" in url.lower():
        raise user_error("unavailable")
    ctx.report("fetching_video", 50)
    out = ctx.tmp_dir / "video.mp4"
    proc = await asyncio.create_subprocess_exec(
        find_tool("ffmpeg"), "-v", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc=d=5:s=640x360:r=25",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-y", str(out),
    )
    ctx.register_process(proc)
    await proc.wait()
    ctx.check_cancelled()
    return out
