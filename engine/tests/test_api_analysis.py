import time

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from djengine.analysis import runner as runner_mod
from djengine.app_paths import AppPaths
from djengine.library import TrackRecord
from djengine.server import build_services, create_app

H = {"X-Token": "t"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "0")
    monkeypatch.setattr(runner_mod, "DEFAULT_TEMPO_METHOD", "librosa")
    monkeypatch.setattr(runner_mod, "DEFAULT_KEY_METHOD", "edma")
    svc = build_services(AppPaths.from_root(tmp_path / "data"), fake=True)
    svc.settings.music_dir = str(tmp_path / "music")
    with TestClient(create_app(svc, token="t")) as c:
        yield c, svc, tmp_path


def jobs(c):
    return c.get("/jobs", headers=H).json()


def wait(c, pred, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        if pred(jobs(c)):
            return jobs(c)
        time.sleep(0.1)
    raise TimeoutError(jobs(c))


def final(js, type_):
    return [j for j in js if j["type"] == type_ and j["status"] in ("done", "failed", "cancelled")]


def song(c):
    return c.get("/search", params={"q": "x", "kind": "songs"}, headers=H).json()[0]


def test_download_triggers_analysis(env):
    c, svc, _ = env
    c.post("/jobs", json={"type": "download", "request": {"target": song(c), "options": {"format": "mp3"}}}, headers=H)
    js = wait(c, lambda js: final(js, "analysis"))
    assert final(js, "analysis")[0]["status"] == "done"
    assert svc.library.list_tracks()[0].camelot


def test_playlist_children_are_analysed(env):
    c, svc, _ = env
    c.post("/jobs", json={"type": "playlist", "id": "PLfake", "options": {"format": "mp3"}}, headers=H)
    js = wait(c, lambda js: len(final(js, "analysis")) == 2 and final(js, "playlist"))
    assert all(j["status"] == "done" for j in final(js, "analysis"))
    assert all(j["parent_id"] is None for j in js if j["type"] == "analysis")


def test_setting_off_means_no_analysis(env):
    c, svc, _ = env
    svc.settings.analyze_on_download = False
    c.post("/jobs", json={"type": "download", "request": {"target": song(c), "options": {"format": "mp3"}}}, headers=H)
    js = wait(c, lambda js: final(js, "download"))
    time.sleep(0.5)
    assert not [j for j in jobs(c) if j["type"] == "analysis"]


def test_cancelled_analysis_keeps_download_done(env):
    c, svc, _ = env
    c.post("/jobs", json={"type": "download", "request": {"target": song(c), "options": {"format": "mp3"}}}, headers=H)
    js = wait(c, lambda js: [j for j in js if j["type"] == "analysis"])
    a = next(j for j in js if j["type"] == "analysis")
    c.delete(f"/jobs/{a['id']}", headers=H)
    js = wait(c, lambda js: final(js, "analysis"))
    assert next(j for j in js if j["type"] == "download")["status"] == "done"


def make_wav(path, seconds=2):
    sf.write(path, np.zeros(44100 * seconds, dtype=np.float32), 44100)
    return path


def test_audio_serving_rules(env, tmp_path):
    c, svc, _ = env
    lib = make_wav(tmp_path / "lib.wav")
    svc.library.add_track(TrackRecord(None, "v", "T", "A", "", 2, None, str(lib), "wav", None, None, ""))
    exe = tmp_path / "evil.exe"
    exe.write_bytes(b"MZ")
    other = make_wav(tmp_path / "other.wav")
    q = lambda p: c.get("/audio", params={"path": str(p), "token": "t"}, headers={"Range": "bytes=0-99"})
    assert c.get("/audio", params={"path": str(lib), "token": "bad"}).status_code == 401
    assert q(lib).status_code == 206 and len(q(lib).content) == 100
    assert q(exe).status_code == 403
    assert q("C:/Windows/win.ini").status_code == 403
    assert q(other).status_code == 403
    assert q(tmp_path / "x" / ".." / "lib.wav").status_code == 206  # same file, normalized
    c.post("/jobs", json={"type": "analysis", "paths": [str(other)]}, headers=H)  # user picked it
    assert q(other).status_code == 206


def test_analysis_endpoints_and_manual_bpm(env, tmp_path, click_track_file):
    c, svc, _ = env
    p = click_track_file(tmp_path / "c.wav")
    assert c.get("/analysis", params={"path": str(p)}, headers=H).status_code == 404
    r = c.post("/jobs", json={"type": "analysis", "paths": [str(p)]}, headers=H).json()
    wait(c, lambda js: final(js, "analysis"))
    got = c.get("/analysis", params={"path": str(p)}, headers=H).json()
    assert abs(got["record"]["bpm"] - 128) <= 1 and len(got["sidecar"]["waveform"]["peaks"]) == 2000
    assert got["info"]["format"] == "wav" and got["info"]["sample_rate"] == 44100
    upd = c.put("/analysis/bpm", json={"path": str(p), "bpm": 127.5}, headers=H).json()
    assert (upd["bpm"], upd["bpm_source"]) == (127.5, "manual")
    from djengine.tags import read_tags

    assert read_tags(p).bpm == 128.0  # TBPM is an integer


def test_harmonic_ordering(env, tmp_path):
    c, svc, _ = env
    rows = [("ref", "8A", 128), ("same", "8A", 126), ("half", "8A", 64), ("adj", "9A", 130), ("rel", "8B", 127),
            ("far", "3A", 128), ("slow", "8A", 150)]
    ids = {}
    for name, cam, bpm in rows:
        f = make_wav(tmp_path / f"{name}.wav", 1)
        ids[name] = svc.library.add_track(TrackRecord(None, name, name, "A", "", 1, None, str(f), "wav", None, None, ""))
        svc.library.set_track_analysis(str(f), bpm, "Am", cam, -9.0)
    res = c.get("/harmonic", params={"ref_track": ids["ref"], "bpm_tolerance": 6}, headers=H).json()
    assert [r["track"]["title"] for r in res] == ["half", "same", "adj", "rel"]
    assert [r["level"] for r in res] == ["same", "same", "adjacent", "relative"]
    manual = c.get("/harmonic", params={"bpm": 128, "camelot": "8A"}, headers=H).json()
    assert "ref" in [r["track"]["title"] for r in manual]


def test_history_includes_bpm_and_key(env):
    c, svc, _ = env
    c.post("/jobs", json={"type": "download", "request": {"target": song(c), "options": {"format": "mp3"}}}, headers=H)
    wait(c, lambda js: final(js, "analysis"))
    h = c.get("/history", headers=H).json()[0]
    assert h["camelot"] and "bpm" in h and h["path"].endswith(".mp3")
