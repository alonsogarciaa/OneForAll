import time

import pytest
from fastapi.testclient import TestClient

from djengine.app_paths import AppPaths
from djengine.server import build_services, create_app

H = {"X-Token": "t"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "0")
    svc = build_services(AppPaths.from_root(tmp_path / "data"), fake=True)
    svc.settings.music_dir = str(tmp_path / "music")
    with TestClient(create_app(svc, token="t")) as c:
        yield c


def wait_job(api, job_id, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        j = next(j for j in api.get("/jobs", headers=H).json() if j["id"] == job_id)
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.05)
    raise TimeoutError


def first_song(api):
    return api.get("/search", params={"q": "graciosa", "kind": "songs"}, headers=H).json()[0]


def test_requires_token(api):
    assert api.get("/jobs").status_code == 401
    assert api.get("/search", params={"q": "x", "kind": "songs"}).status_code == 401


def test_download_then_duplicate_409(api):
    song = first_song(api)
    body = {"type": "download", "request": {"target": song, "options": {"format": "mp3", "quality": "320"}}}
    r = api.post("/jobs", json=body, headers=H)
    assert r.status_code == 200
    assert wait_job(api, r.json()["job"]["id"])["status"] == "done"
    assert api.get("/search", params={"q": "graciosa", "kind": "songs"}, headers=H).json()[0]["in_library"] is True
    r2 = api.post("/jobs", json=body, headers=H)
    assert r2.status_code == 409 and r2.json()["duplicate"]["title"] == song["title"]
    body["request"]["force"] = True
    assert api.post("/jobs", json=body, headers=H).status_code == 200


def test_history_delete_ids_and_all(api):
    song = first_song(api)
    for force in (False, True):
        body = {"type": "download", "request": {"target": song, "options": {"format": "mp3"}, "force": force}}
        wait_job(api, api.post("/jobs", json=body, headers=H).json()["job"]["id"])
    hist = api.get("/history", headers=H).json()
    assert len(hist) == 2
    assert api.request("DELETE", "/history", json={"ids": [hist[0]["id"]]}, headers=H).json() == {"deleted": 1}
    assert api.request("DELETE", "/history", json={"all": True}, headers=H).json() == {"deleted": 1}


def test_active_count_and_cancel(api, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "5")
    body = {"type": "download", "request": {"target": first_song(api), "options": {"format": "mp3"}}}
    job = api.post("/jobs", json=body, headers=H).json()["job"]
    time.sleep(0.2)
    ac = api.get("/jobs/active-count", headers=H).json()
    assert ac["count"] == 1 and ac["by_type"] == {"download": 1}
    assert api.delete(f"/jobs/{job['id']}", headers=H).json() == {"cancelled": True}
    assert wait_job(api, job["id"])["status"] == "cancelled"


def test_settings_updates_concurrency(api):
    s = api.get("/settings", headers=H).json()
    s["download_concurrency"] = 5
    assert api.put("/settings", json=s, headers=H).status_code == 200
    s["download_concurrency"] = 9
    assert api.put("/settings", json=s, headers=H).status_code == 422


def test_ws_hello_and_job_done(api):
    with pytest.raises(Exception):
        with api.websocket_connect("/events?token=bad") as ws:
            ws.receive_json()
    with api.websocket_connect("/events?token=t") as ws:
        assert ws.receive_json() == {"type": "engine.hello"}
        body = {"type": "download", "request": {"target": first_song(api), "options": {"format": "mp3"}}}
        api.post("/jobs", json=body, headers=H)
        types = []
        while "job.done" not in types:
            types.append(ws.receive_json()["type"])
        assert types[0] == "job.queued"


def test_playlist_and_convert_endpoints(api, sine_wav, tmp_path):
    r = api.post("/jobs", json={"type": "playlist", "id": "PLfake", "options": {"format": "mp3"}}, headers=H)
    j = wait_job(api, r.json()["job"]["id"])
    assert j["result"]["done"] == 2 and len(j["result"]["failed"]) == 1
    src = tmp_path / "a.wav"
    src.write_bytes(sine_wav.read_bytes())
    r = api.post("/jobs", json={"type": "convert", "paths": [str(src)], "options": {"format": "opus"}}, headers=H)
    assert wait_job(api, r.json()["jobs"][0]["id"])["status"] == "done"
    assert (tmp_path / "a.opus").exists()
