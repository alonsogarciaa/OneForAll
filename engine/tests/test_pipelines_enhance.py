import time

import pytest
from fastapi.testclient import TestClient

from djengine.app_paths import AppPaths
from djengine.server import build_services, create_app

from .test_api_stems import H, final, jobs, song, wait


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "0")
    svc = build_services(AppPaths.from_root(tmp_path / "data"), fake=True)
    svc.settings.music_dir = str(tmp_path / "music")
    svc.settings.analyze_on_download = False
    with TestClient(create_app(svc, token="t")) as c:
        yield c, svc


def _download(c, then_stems=False):
    req = {"target": song(c), "options": {"format": "mp3"}}
    if then_stems:
        req["then_stems"] = {"stems": ["vocals"], "karaoke": False}
    c.post("/jobs", json={"type": "download", "request": req}, headers=H)
    return wait(c, lambda js: final(js, "download"))


def test_settings_defaults():
    from djengine.settings import Settings

    s = Settings()
    assert (s.enhance_on_download, s.enhance_mode, s.enhance_format) == (False, "replace", "same")


def test_off_by_default_no_enhance(env):
    c, _ = env
    _download(c)
    time.sleep(0.3)
    assert not [j for j in jobs(c) if j["type"] == "enhance"]


def test_on_queues_top_level_enhance_with_settings(env):
    c, svc = env
    svc.settings.enhance_on_download = True
    svc.settings.enhance_mode = "copy"
    svc.settings.enhance_format = "flac"
    js = _download(c)
    path = final(js, "download")[0]["result"]["path"]
    js = wait(c, lambda js: final(js, "enhance"))
    e = final(js, "enhance")[0]
    assert e["parent_id"] is None and e["status"] == "done", e
    assert e["result"]["path"].endswith("(Mejorado).flac") and e["payload"]["path"] == path


def test_stems_wait_for_the_enhanced_file(env):
    c, svc = env
    svc.settings.enhance_on_download = True
    svc.settings.enhance_mode = "copy"
    js = _download(c, then_stems=True)
    js = wait(c, lambda js: final(js, "enhance") and final(js, "stems"))
    e, s = final(js, "enhance")[0], final(js, "stems")[0]
    assert s["payload"]["paths"] == [e["result"]["path"]]
    assert len([j for j in js if j["type"] == "stems"]) == 1


def test_analysis_runs_on_the_final_file(env):
    c, svc = env
    svc.settings.analyze_on_download = True
    svc.settings.enhance_on_download = True
    svc.settings.enhance_mode = "copy"
    _download(c)
    js = wait(c, lambda js: final(js, "enhance") and final(js, "analysis"))
    e = final(js, "enhance")[0]
    assert [j["payload"]["paths"] for j in js if j["type"] == "analysis"] == [[e["result"]["path"]]]


def test_replace_same_analyses_after_the_enhance(env):
    c, svc = env
    svc.settings.analyze_on_download = True
    svc.settings.enhance_on_download = True
    js = _download(c)
    path = final(js, "download")[0]["result"]["path"]
    assert not [j for j in jobs(c) if j["type"] == "analysis" and j["status"] not in ("queued",)
                and not final(jobs(c), "enhance")]  # never while the file is being replaced
    js = wait(c, lambda js: final(js, "enhance") and final(js, "analysis"))
    assert [j["payload"]["paths"] for j in js if j["type"] == "analysis"] == [[path]]
    e = final(js, "enhance")[0]
    assert e["result"]["path"] == path
