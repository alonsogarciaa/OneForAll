import json
from pathlib import Path

import pytest

from djengine.search import SearchService, filter_results, parse_views, resolve_url

RAW = json.loads((Path(__file__).parent / "fixtures" / "ytm_raw.json").read_text(encoding="utf-8"))


class StubYTM:
    def search(self, q, filter=None, limit=20):
        return RAW[filter]

    def get_playlist(self, playlist_id, limit=100):
        return RAW["playlist"]

    def get_song(self, video_id):
        return RAW["song_details"]


class Exploding:
    def search(self, *a, **k):
        raise RuntimeError("ytm down")


@pytest.fixture
def svc():
    return SearchService(ytm=StubYTM())


def test_songs_mapped_and_broken_dropped(svc):
    r = svc.search("la graciosa quevedo", "songs")
    assert r[0].kind == "song" and r[0].title == "LA GRACIOSA"
    assert r[0].artist == "Quevedo, Elvis Crespo" and r[0].duration_s == 258 and r[0].views == 72_000_000
    assert r[0].album == "EL BAIFO" and r[0].url == "https://music.youtube.com/watch?v=Kev3r6W4TPo"
    assert r[0].thumbnail.startswith("https://")
    assert all(x.title and x.duration_s for x in r)
    assert not any("BROKEN" in x.title for x in r)


def test_videos_and_playlists(svc):
    v = svc.search("x", "videos")
    assert v and v[0].kind == "video" and v[0].duration_s
    p = svc.search("x", "playlists")
    assert p and p[0].kind == "playlist" and not p[0].id.startswith("VL")


def test_parse_views():
    assert parse_views("1.2M") == 1_200_000
    assert parse_views("350K views") == 350_000
    assert parse_views("12,345") == 12345
    assert parse_views("2.1B") == 2_100_000_000
    assert parse_views(None) is None and parse_views("") is None


@pytest.mark.parametrize("u,exp", [
    ("https://youtu.be/abc123", ("song", "abc123")),
    ("https://music.youtube.com/watch?v=abc123&list=PLx", ("song", "abc123")),
    ("https://www.youtube.com/watch?v=abc123", ("song", "abc123")),
    ("https://www.youtube.com/shorts/abc123", ("song", "abc123")),
    ("https://www.youtube.com/playlist?list=PLx", ("playlist", "PLx")),
    ("la graciosa", None),
])
def test_resolve_url(u, exp):
    assert resolve_url(u) == exp


def test_search_with_song_url_returns_single(svc):
    r = svc.search("https://youtu.be/abc123", "songs")
    assert len(r) == 1 and r[0].id == "abc123" and r[0].title == "Single Song" and r[0].duration_s == 201


def test_fallback_on_ytm_error():
    entries = [
        {"id": "a", "title": "Good", "channel": "Ch", "duration": 200, "view_count": 10},
        {"id": "b", "title": "No duration", "channel": "Ch", "duration": None},
    ]
    svc = SearchService(ytm=Exploding(), fallback=lambda q: entries)
    r = svc.search("x", "songs")
    assert [x.id for x in r] == ["a"] and r[0].kind == "video"


def test_filter_song_duration_window():
    from djengine.search import SearchResult

    mk = lambda d, k="song": SearchResult(kind=k, id="i", title="t", artist="a", duration_s=d, views=None, thumbnail=None, url="u")
    assert [x.duration_s for x in filter_results([mk(30), mk(200), mk(1500)])] == [200]
    assert [x.duration_s for x in filter_results([mk(30, "video"), mk(3600, "video")])] == [3600]


def test_playlist(svc):
    pl = svc.get_playlist("PLx")
    assert pl.title and len(pl.tracks) >= 1 and pl.tracks[0].kind == "song"


@pytest.mark.online
def test_search_online():
    r = SearchService().search("la graciosa quevedo", "songs")
    assert any("graciosa" in x.title.lower() for x in r[:3])
