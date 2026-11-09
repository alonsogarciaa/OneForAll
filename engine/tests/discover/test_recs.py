# ytm_*.json captured 2026-11-09 with ytmusicapi: get_watch_playlist("Kev3r6W4TPo", radio=True, limit=30),
# get_mood_categories(), get_mood_playlists(<Chill params>)[:6].
import json
from pathlib import Path

from fastapi.testclient import TestClient

from djengine.discover.recs import seed_for_track
from djengine.library import TrackRecord
from djengine.search import SearchService
from djengine.server import create_app
from tests.export.test_model import svc  # noqa: F401  (fixture)

FIX = Path(__file__).parent / "fixtures"
H = {"X-Token": "t"}


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class Ytm:
    def __init__(self):
        self.calls = []

    def get_watch_playlist(self, videoId, radio=False, limit=25):
        self.calls.append(("watch", videoId, radio, limit))
        return load("ytm_watch_radio.json")

    def get_mood_categories(self):
        return load("ytm_moods.json")

    def get_mood_playlists(self, params):
        self.calls.append(("mood", params))
        return load("ytm_mood_playlists.json")


def test_similar_from_radio_fixture():
    ytm = Ytm()
    rs = SearchService(ytm=ytm).similar("Kev3r6W4TPo")
    assert ytm.calls == [("watch", "Kev3r6W4TPo", True, 50)]
    ids = [r.id for r in rs]
    assert "Kev3r6W4TPo" not in ids and len(ids) == len(set(ids)) and len(ids) >= 20
    assert all(r.kind == "song" and r.duration_s and r.duration_s >= 60 for r in rs)
    assert all(r.artist for r in rs)


def test_moods_and_mood_playlists():
    s = SearchService(ytm=Ytm())
    sections = s.moods()
    assert [x["title"] for x in sections] == ["Moods & moments", "Genres"]
    assert sections[0]["items"][0] == {"title": "Chill", "params": "ggMPOg1uX1JOQWZFeDByc2Jm"}
    pls = s.mood_playlists("ggMPOg1uX1JOQWZFeDByc2Jm")
    assert pls and all(p.kind == "playlist" and p.id for p in pls)
    assert pls[0].title == "Coffee Shop Blend" and pls[0].id.startswith("RDCLAK")


def test_seed_uses_video_id_or_searches(svc):  # noqa: F811
    t = TrackRecord(1, "abc", "La Graciosa", "Quevedo", "", 200, None, "C:/a.mp3", "mp3", None, None, "")
    assert seed_for_track(svc, t) == "abc"
    own = TrackRecord(2, None, "La Graciosa", "Quevedo", "", 200, None, "C:/b.mp3", "mp3", None, None, "")
    assert seed_for_track(svc, own) == svc.search.search("Quevedo La Graciosa", "songs")[0].id
    copy = TrackRecord(3, None, "x", "y", "", 200, None, "C:/c.mp3", "mp3", None, None, "", origin_video_id="orig")
    assert seed_for_track(svc, copy) == "orig"


def test_seed_without_matches_gives_none(svc, monkeypatch):  # noqa: F811
    monkeypatch.setattr(svc.search, "search", lambda q, k: [])
    t = TrackRecord(2, None, "Nada", "Nadie", "", 200, None, "C:/b.mp3", "mp3", None, None, "")
    assert seed_for_track(svc, t) is None


def test_routes(svc):  # noqa: F811
    tid = svc.library.add_track(TrackRecord(None, "fake1", "La Graciosa", "Fake Artist", "", 200, None, "C:/a.mp3", "mp3",
                                            None, None, ""))
    with TestClient(create_app(svc, token="t")) as c:
        r = c.get("/discover/similar", params={"track_id": tid}, headers=H).json()
        assert r["seed"]["id"] == "fake1" and len(r["items"]) >= 5
        assert {"bpm", "camelot", "analysed"} <= set(r["items"][0])
        assert c.get("/discover/similar", params={"video_id": "fake1"}, headers=H).status_code == 200
        assert c.get("/discover/similar", params={"track_id": 9999}, headers=H).status_code == 404
        assert c.get("/discover/similar", headers=H).status_code == 422
        moods = c.get("/discover/moods", headers=H).json()
        assert moods and moods[0]["items"]
        pls = c.get("/discover/mood", params={"params": moods[0]["items"][0]["params"]}, headers=H).json()
        assert pls and pls[0]["kind"] == "playlist"


def test_no_seed_gives_empty_list(svc, monkeypatch):  # noqa: F811
    monkeypatch.setattr(svc.search, "search", lambda q, k: [])
    tid = svc.library.add_track(TrackRecord(None, None, "Nada", "Nadie", "", 200, None, "C:/n.mp3", "mp3", None, None, ""))
    with TestClient(create_app(svc, token="t")) as c:
        assert c.get("/discover/similar", params={"track_id": tid}, headers=H).json() == {"seed": None, "items": []}
