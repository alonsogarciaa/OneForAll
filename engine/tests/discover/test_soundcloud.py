import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from djengine.search import SearchService, soundcloud_results
from djengine.server import create_app
from tests.export.test_model import svc  # noqa: F401  (fixture)

FIX = Path(__file__).parent / "fixtures"
H = {"X-Token": "t"}


def test_parse_scsearch_output():
    entries = json.loads((FIX / "sc_search.json").read_text(encoding="utf-8"))["entries"]
    rs = soundcloud_results(entries)
    assert all(r.kind == "soundcloud" and r.source == "soundcloud" and r.id.startswith("sc:") for r in rs)
    assert rs[0].id == "sc:2310783158" and rs[0].title == "LA GRACIOSA" and rs[0].artist == "QUEVEDO"
    assert rs[0].duration_s == 258 and not rs[0].preview_only
    go = [r for r in rs if r.title == "Go+ only"]
    assert go and go[0].preview_only


def test_short_non_preview_tracks_are_dropped():
    rs = soundcloud_results([{"id": "1", "url": "https://x", "title": "Intro", "duration": 20, "uploader": "A"}])
    assert rs == []


def test_service_uses_scsearch25():
    seen = []
    s = SearchService(ytm=object(), sc_fetch=lambda q: seen.append(q) or [])
    assert s.search("quevedo", "soundcloud") == [] and seen == ["scsearch25:quevedo"]


def _wait(c, pred, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        js = c.get("/jobs", headers=H).json()
        if pred(js):
            return js
        time.sleep(0.1)
    raise TimeoutError


def test_search_download_and_in_library(svc, tmp_path):  # noqa: F811
    svc.settings.music_dir = str(tmp_path / "music")
    svc.settings.analyze_on_download = False
    with TestClient(create_app(svc, token="t")) as c:
        rs = c.get("/search", params={"q": "x", "kind": "soundcloud"}, headers=H).json()
        target = next(r for r in rs if not r["preview_only"])
        assert target["id"].startswith("sc:")
        c.post("/jobs", json={"type": "download", "request": {"target": target, "options": {"format": "mp3"}}}, headers=H)
        _wait(c, lambda js: any(j["type"] == "download" and j["status"] == "done" for j in js))
        lib = c.get("/library", headers=H).json()
        assert lib[0]["video_id"] == target["id"]
        again = c.get("/search", params={"q": "x", "kind": "soundcloud"}, headers=H).json()
        assert next(r for r in again if r["id"] == target["id"])["in_library"] is True


def test_preview_only_cannot_be_downloaded(svc):  # noqa: F811
    with TestClient(create_app(svc, token="t")) as c:
        rs = c.get("/search", params={"q": "x", "kind": "soundcloud"}, headers=H).json()
        go = next(r for r in rs if r["preview_only"])
        r = c.post("/jobs", json={"type": "download", "request": {"target": go, "options": {"format": "mp3"}}}, headers=H)
        assert r.status_code == 422 and r.json()["detail"]["message"] == "Solo vista previa"
