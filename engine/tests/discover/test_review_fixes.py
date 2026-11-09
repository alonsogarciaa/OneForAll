"""Phase 5a final review: engine fixes."""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from djengine.discover.links import ImportItem, parse_link, read_apple, read_soundcloud
from djengine.discover.match import match
from djengine.discover.quick import lookup, make_quick_runner
from djengine.fakes import SONGS
from djengine.library import TrackRecord
from djengine.search import SearchResult
from djengine.server import create_app
from tests.export.test_model import svc  # noqa: F401  (fixture)

FIX = Path(__file__).parent / "fixtures"
H = {"X-Token": "t"}


def test_quick_analysis_uses_the_app_estimators_from_the_start():
    code = ("import djengine.discover.quick, djengine.server;"
            "from djengine.analysis.tempo import TEMPO_METHODS; from djengine.analysis.key import KEY_METHODS;"
            "print('deeprhythm' in TEMPO_METHODS, 'cnn' in KEY_METHODS)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=Path(__file__).parents[2])
    assert out.stdout.strip() == "True True", out.stderr[-500:]


def test_apple_song_link_imports_only_that_song():
    html = (FIX / "apple_playlist.html").read_text(encoding="utf-8")
    song_id = json.loads(html.split('server-data">', 1)[1].split("</script>")[0])[
        "data"][0]["data"]["sections"][1]["items"][1]["id"].rsplit(" - ", 1)[1]
    link = parse_link(f"https://music.apple.com/us/album/x/123?i={song_id}")
    lst = read_apple(link, fetch=lambda u: html)
    assert [i.title for i in lst.items] == ["Been By Now"]


def test_live_version_in_a_noise_bracket_does_not_tie_the_original():
    item = ImportItem(title="Song", artist="A", duration_s=200)

    class S:
        def search(self, q, kind):
            mk = lambda i, t: SearchResult(kind="song", id=i, title=t, artist="A", duration_s=200, views=None,
                                           thumbnail=None, url="u")
            return [mk("live", "Song (Official Live Video)"), mk("orig", "Song")]

    assert match(S(), item).best.id == "orig"


def test_soundcloud_set_with_thin_entries_and_go_plus():
    data = {"_type": "playlist", "title": "Set", "uploader": "DJ Set Owner", "entries": [
        {"id": "1", "url": "https://api.soundcloud.com/tracks/1", "title": "Thin"},
        {"id": "2", "url": "https://api.soundcloud.com/tracks/2", "title": "Preview", "duration": 30.0, "uploader": "X"}]}
    lst = read_soundcloud(parse_link("https://soundcloud.com/dj/sets/mix"), run=lambda url: data)
    thin, prev = lst.items
    assert thin.artist == "DJ Set Owner" and not thin.preview_only
    assert prev.preview_only


def test_import_links_owned_tracks_into_the_playlist(svc, tmp_path):  # noqa: F811
    svc.settings.music_dir = str(tmp_path / "music")
    svc.settings.analyze_on_download = False
    owned = tmp_path / "owned.mp3"
    owned.write_bytes(b"x")
    tid = svc.library.add_track(TrackRecord(None, SONGS[0].id, SONGS[0].title, SONGS[0].artist, "", 5, None, str(owned),
                                            "mp3", None, None, ""))
    with TestClient(create_app(svc, token="t")) as c:
        c.post("/jobs", json={"type": "import", "name": "Lista", "targets": [s.model_dump() for s in SONGS],
                              "options": {"format": "mp3"}}, headers=H)
        end = time.time() + 60
        while time.time() < end and not any(j["type"] == "playlist" and j["status"] == "done"
                                            for j in c.get("/jobs", headers=H).json()):
            time.sleep(0.1)
    pl = svc.library.list_playlists()[0][0]
    ids = svc.library.playlist_track_ids(pl)
    assert len(ids) == 3 and tid in ids  # the owned song is in the playlist too, not only the new ones


async def test_cancel_stops_every_clip_and_caches_no_failure(svc, monkeypatch):  # noqa: F811
    async def bc(e):
        pass

    monkeypatch.setattr(svc.hub, "broadcast", bc)
    real = svc.clip_downloader
    started = []

    async def slow(ctx, url, start_s, seconds=60):
        started.append(time.monotonic())
        await asyncio.sleep(0.3)
        ctx.check_cancelled()  # like the real downloader: cancelled between steps
        return await real(ctx, url, start_s, seconds)

    svc.clip_downloader = slow
    ids = [f"k{i}" for i in range(12)]
    job = svc.jobs.submit("quick_analysis", "t", make_quick_runner(svc, ids, [200] * 12))
    while not started:
        await asyncio.sleep(0.01)
    await svc.jobs.cancel(job.id)
    while svc.jobs.get(job.id).status not in ("done", "failed", "cancelled"):
        await asyncio.sleep(0.02)
    ended = time.monotonic()
    await asyncio.sleep(1.5)  # orphan tasks would keep downloading here
    assert not [t for t in started if t > ended]
    assert all(not v["failed"] for v in lookup(svc, ids).values())


def test_version_words_are_whole_words():
    item = ImportItem(title="Deliver", artist="A", duration_s=200)

    class S:
        def search(self, q, kind):
            return [SearchResult(kind="song", id="x", title="Deliver", artist="A", duration_s=200, views=None,
                                 thumbnail=None, url="u")]

    assert match(S(), item).status == "found"
