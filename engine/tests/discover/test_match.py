import asyncio

import pytest

from djengine.discover.links import ImportItem
from djengine.discover.match import make_match_runner, match, score
from djengine.search import SearchResult
from tests.export.test_model import svc  # noqa: F401  (fixture)


def cand(title, artist, dur, id_="v"):
    return SearchResult(kind="song", id=id_, title=title, artist=artist, duration_s=dur, views=None, thumbnail=None,
                        url=f"https://music.youtube.com/watch?v={id_}")


class Search:
    def __init__(self, results):
        self.results = results
        self.queries = []

    def search(self, q, kind):
        self.queries.append((q, kind))
        return list(self.results)


def test_exact_is_found():
    it = ImportItem(title="La Graciosa", artist="Quevedo", duration_s=200)
    r = match(Search([cand("La Graciosa", "Quevedo", 201)]), it)
    assert r.status == "found" and r.best.id == "v" and score(it, r.best) >= 0.8


def test_query_is_artist_and_title():
    s = Search([])
    match(s, ImportItem(title="Song", artist="A, B", duration_s=200))
    assert s.queries == [("A, B Song", "songs")]


def test_feat_and_multiple_artists_found():
    it = ImportItem(title="Song (feat. B)", artist="A, B", duration_s=200)
    assert match(Search([cand("Song", "A", 199)]), it).status == "found"


def test_remix_does_not_beat_original():
    it = ImportItem(title="Song", artist="A", duration_s=200)
    r = match(Search([cand("Song (Remix)", "A", 240, "rmx"), cand("Song", "A", 200, "orig")]), it)
    assert r.best.id == "orig" and [a.id for a in r.alternatives] == ["rmx"]


def test_remix_requested_picks_remix():
    it = ImportItem(title="Song - Remix", artist="A", duration_s=240)
    r = match(Search([cand("Song", "A", 200, "orig"), cand("Song (Remix)", "A", 240, "rmx")]), it)
    assert r.best.id == "rmx"


def test_duration_far_off_goes_to_review():
    it = ImportItem(title="Song", artist="A", duration_s=200)
    assert match(Search([cand("Song", "A", 230)]), it).status == "review"


def test_unknown_duration_is_not_punished_too_much():
    it = ImportItem(title="Song", artist="A", duration_s=None)
    assert match(Search([cand("Song", "A", 230)]), it).status == "found"


def test_wrong_song_is_missing():
    it = ImportItem(title="Despacito", artist="Luis Fonsi", duration_s=228)
    assert match(Search([cand("Bohemian Rhapsody", "Queen", 355)]), it).status == "missing"


def test_nothing_is_missing():
    r = match(Search([]), ImportItem(title="Song", artist="A", duration_s=200))
    assert r.status == "missing" and r.best is None and r.alternatives == []


def test_alternatives_capped_at_3():
    it = ImportItem(title="Song", artist="A", duration_s=200)
    r = match(Search([cand("Song", "A", 200, f"v{i}") for i in range(6)]), it)
    assert len(r.alternatives) == 3


def test_search_errors_are_missing_not_crash():
    class Broken:
        def search(self, q, kind):
            raise RuntimeError("offline")

    assert match(Broken(), ImportItem(title="Song", artist="A", duration_s=200)).status == "missing"


async def test_import_match_job_emits_one_event_per_item(svc, monkeypatch):  # noqa: F811
    events = []

    async def bc(e):
        events.append(e)

    monkeypatch.setattr(svc.hub, "broadcast", bc)
    svc.search = Search([cand("Song", "A", 200)])
    items = [ImportItem(title="Song", artist="A", duration_s=200) for _ in range(5)]
    job = svc.jobs.submit("import_match", "t", make_match_runner(svc, items))
    while svc.jobs.get(job.id).status not in ("done", "failed", "cancelled"):
        await asyncio.sleep(0.02)
    j = svc.jobs.get(job.id)
    assert j.status == "done" and len(j.result["results"]) == 5
    got = sorted(e["index"] for e in events if e["type"] == "match.result")
    assert got == [0, 1, 2, 3, 4] and all(e["job_id"] == job.id for e in events if e["type"] == "match.result")


def test_import_match_api(svc):  # noqa: F811
    from fastapi.testclient import TestClient

    from djengine.server import create_app

    with TestClient(create_app(svc, token="t")) as c:
        r = c.post("/jobs", json={"type": "import_match", "items": [{"title": "Song", "artist": "A", "duration_s": 200}]},
                   headers={"X-Token": "t"})
        assert r.status_code == 200 and r.json()["job"]["type"] == "import_match"
        assert c.post("/jobs", json={"type": "import_match", "items": []}, headers={"X-Token": "t"}).status_code == 422
