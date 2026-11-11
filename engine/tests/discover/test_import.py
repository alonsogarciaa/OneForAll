import time

import pytest
from fastapi.testclient import TestClient

from djengine.discover.links import ImportList
from djengine.errors import UserError
from djengine.fakes import SONGS
from djengine.library import TrackRecord
from djengine.server import create_app
from tests.export.test_model import svc  # noqa: F401  (fixture)

H = {"X-Token": "t"}
FINAL = ("done", "failed", "cancelled")


@pytest.fixture
def c(svc, tmp_path):  # noqa: F811
    svc.settings.music_dir = str(tmp_path / "music")
    svc.settings.analyze_on_download = False
    with TestClient(create_app(svc, token="t")) as client:
        yield client, svc, tmp_path


def _wait_import(client):
    end = time.time() + 60
    while time.time() < end:
        js = client.get("/jobs", headers=H).json()
        imp = [j for j in js if j["type"] == "playlist" and j["status"] in FINAL]
        if imp:
            return imp[0]
        time.sleep(0.1)
    raise TimeoutError


def test_import_creates_the_playlist(c):
    client, svc, tmp = c
    targets = [s.model_dump() for s in SONGS]
    r = client.post("/jobs", json={"type": "import", "name": "Mi lista", "targets": targets,
                                   "options": {"format": "mp3"}}, headers=H)
    assert r.status_code == 200, r.text
    job = _wait_import(client)
    assert job["status"] == "done" and job["result"]["done"] == 3
    pls = svc.library.list_playlists()
    assert [name for _, name in pls] == ["Mi lista"]
    assert len(svc.library.playlist_track_ids(pls[0][0])) == 3
    assert len(list((tmp / "music" / "Mi lista").glob("*.mp3"))) == 3


def test_tracks_already_in_the_library_are_skipped(c):
    client, svc, tmp = c
    svc.library.add_track(TrackRecord(None, SONGS[0].id, SONGS[0].title, SONGS[0].artist, "", 5, None,
                                      str(tmp / "x.mp3"), "mp3", None, None, ""))
    (tmp / "x.mp3").write_bytes(b"x")
    client.post("/jobs", json={"type": "import", "name": "Otra", "targets": [s.model_dump() for s in SONGS],
                               "options": {"format": "mp3"}}, headers=H)
    job = _wait_import(client)
    assert job["result"]["skipped"] == 1 and job["result"]["done"] == 2


def test_empty_import_is_refused_and_creates_nothing(c):
    client, svc, _ = c
    r = client.post("/jobs", json={"type": "import", "name": "Vacía", "targets": [], "options": {"format": "mp3"}}, headers=H)
    assert r.status_code == 422 and svc.library.list_playlists() == []


def test_read_link_route(c):
    client, svc, _ = c
    r = client.post("/discover/link", json={"text": "https://open.spotify.com/playlist/abc"}, headers=H)
    assert r.status_code == 200
    lst = ImportList.model_validate(r.json())
    assert lst.service == "spotify" and lst.items


def test_read_link_errors(c, monkeypatch):
    client, svc, _ = c
    assert client.post("/discover/link", json={"text": "hola"}, headers=H).json()["detail"]["message"] == \
        "No se pudo leer el enlace"

    def changed(text):
        raise UserError("source_changed", "Spotify ha cambiado; actualiza la app")

    monkeypatch.setattr(svc.search, "read_link", changed)
    r = client.post("/discover/link", json={"text": "https://open.spotify.com/playlist/abc"}, headers=H)
    assert r.status_code == 422 and r.json()["detail"]["message"] == "Spotify ha cambiado; actualiza la app"


def test_soundcloud_items_carry_their_id(c):
    client, _, _ = c
    lst = client.post("/discover/link", json={"text": "https://soundcloud.com/fake/sets/mix"}, headers=H).json()
    assert lst["service"] == "soundcloud" and all(i["id"].startswith("sc:") and i["url"] for i in lst["items"])
