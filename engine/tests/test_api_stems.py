import time
import zipfile

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from djengine.app_paths import AppPaths
from djengine.server import build_services, create_app

H = {"X-Token": "t"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "0")
    svc = build_services(AppPaths.from_root(tmp_path / "data"), fake=True)
    svc.settings.music_dir = str(tmp_path / "music")
    svc.settings.analyze_on_download = False
    with TestClient(create_app(svc, token="t")) as c:
        yield c, svc, tmp_path


def jobs(c):
    return c.get("/jobs", headers=H).json()


def wait(c, pred, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        js = jobs(c)
        if pred(js):
            return js
        time.sleep(0.1)
    raise TimeoutError(jobs(c))


def final(js, t):
    return [j for j in js if j["type"] == t and j["status"] in ("done", "failed", "cancelled")]


def wav(tmp_path, name="s.wav"):
    p = tmp_path / name
    sf.write(p, np.random.default_rng(0).normal(0, 0.1, (44100 * 2, 2)).astype(np.float32), 44100)
    return p


def test_stems_job_listing_zip_and_audio(env):
    c, svc, tmp = env
    p = wav(tmp)
    r = c.post("/jobs", json={"type": "stems", "paths": [str(p)], "stems": ["vocals", "drums", "bass"]}, headers=H)
    assert r.status_code == 200
    wait(c, lambda js: final(js, "stems"))
    got = c.get("/stems", params={"path": str(p)}, headers=H).json()
    assert sorted(s["stem"] for s in got["stems"]) == ["bass", "drums", "vocals"]
    z = c.post("/stems/zip", json={"path": str(p)}, headers=H).json()["zip"]
    assert sorted(zipfile.ZipFile(z).namelist()) == ["bass.wav", "drums.wav", "vocals.wav"]
    stem_file = next(s["file"] for s in got["stems"] if s["stem"] == "vocals")
    ok = c.get("/audio", params={"path": stem_file, "token": "t"}, headers={"Range": "bytes=0-9"})
    assert ok.status_code == 206
    other = wav(tmp, "not_a_stem.wav")
    assert c.get("/audio", params={"path": str(other), "token": "t"}).status_code == 403


def test_unknown_stem_and_empty_list_rejected(env):
    c, _, tmp = env
    p = wav(tmp)
    assert c.post("/jobs", json={"type": "stems", "paths": [str(p)], "stems": ["voice"]}, headers=H).status_code == 422
    assert c.post("/jobs", json={"type": "stems", "paths": [str(p)], "stems": []}, headers=H).status_code == 422


def song(c):
    return c.get("/search", params={"q": "x", "kind": "songs"}, headers=H).json()[0]


def test_download_then_stems(env):
    c, svc, _ = env
    body = {"type": "download", "request": {"target": song(c), "options": {"format": "mp3"},
                                            "then_stems": {"stems": ["vocals"], "karaoke": False}}}
    c.post("/jobs", json=body, headers=H)
    js = wait(c, lambda js: final(js, "stems"))
    assert final(js, "stems")[0]["status"] == "done"
    lib = c.get("/library", headers=H).json()
    assert lib[0]["has_stems"] is True


def test_failed_download_queues_no_stems(env):
    c, svc, _ = env
    pl = c.get("/playlist/PLfake", headers=H).json()
    private = next(t for t in pl["tracks"] if "private" in t["id"])
    body = {"type": "download", "request": {"target": private, "options": {"format": "mp3"},
                                            "then_stems": {"stems": ["vocals"], "karaoke": False}}}
    c.post("/jobs", json=body, headers=H)
    wait(c, lambda js: final(js, "download"))
    time.sleep(0.3)
    assert not [j for j in jobs(c) if j["type"] == "stems"]


def test_cancelled_stems_keeps_download_done(env, monkeypatch):
    c, svc, _ = env
    import djengine.stems.separate as sep

    real = sep.FakeSeparator.separate

    def slow(self, audio, sr, progress, cancelled):
        for _ in range(100):
            if cancelled():
                from djengine.errors import JobCancelled

                raise JobCancelled()
            time.sleep(0.05)
        return real(self, audio, sr, progress, cancelled)

    monkeypatch.setattr(sep.FakeSeparator, "separate", slow)
    body = {"type": "download", "request": {"target": song(c), "options": {"format": "mp3"},
                                            "then_stems": {"stems": ["vocals"], "karaoke": False}}}
    c.post("/jobs", json=body, headers=H)
    js = wait(c, lambda js: [j for j in js if j["type"] == "stems" and j["status"] == "running"])
    sj = next(j for j in js if j["type"] == "stems")
    c.delete(f"/jobs/{sj['id']}", headers=H)
    js = wait(c, lambda js: final(js, "stems"))
    assert final(js, "stems")[0]["status"] == "cancelled"
    assert next(j for j in js if j["type"] == "download")["status"] == "done"


def test_stems_check_only_confirms_our_stems(env):
    c, svc, tmp = env
    stem = tmp / "vocals.wav"
    stem.write_bytes(b"x")
    src = tmp / "song.wav"
    src.write_bytes(b"y")
    svc.stems.add(src, "vocals", stem, "m")
    r = c.post("/stems/check", json={"files": [str(stem), str(src), "C:/Windows/win.ini"]}, headers=H).json()
    assert r == {"stems": [str(stem)]}
