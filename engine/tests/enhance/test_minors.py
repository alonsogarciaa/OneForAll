"""Phase 4b review minors (M1-M10, M14)."""
import asyncio
import os
import pickle
import subprocess
from pathlib import Path

import pytest

from djengine.app_paths import AppPaths
from djengine.enhance import models as em
from djengine.enhance import runner as er
from djengine.enhance.runner import submit_enhance, target_codec
from djengine.server import build_services, create_app
from djengine.tools import find_tool

from .test_runner import FINAL, _make, _run, _wait, song, svc  # noqa: F401  (fixtures)

H = {"X-Token": "t"}


async def test_bookkeeping_failure_after_commit_still_reports_done(svc, song, monkeypatch):  # noqa: F811
    def boom(*a, **k):
        raise RuntimeError("decode failed")

    monkeypatch.setattr(er, "_save_analysis", boom)
    job = await _run(svc, song, "replace", "flac")
    assert job.status == "done", job.error
    flac = song.with_suffix(".flac")
    assert flac.is_file() and svc.library.track_by_path(str(flac)) is not None  # the library still follows the file


def test_put_settings_keeps_the_measured_speed(svc):  # noqa: F811
    from fastapi.testclient import TestClient

    svc.settings.enhance_rtf = 3.5
    with TestClient(create_app(svc, token="t")) as c:
        s = c.get("/settings", headers=H).json()
        s["enhance_rtf"] = None  # the UI's copy from before the measurement
        s["tinted"] = True
        r = c.put("/settings", json=s, headers=H)
        assert r.status_code == 200 and r.json()["enhance_rtf"] == 3.5 and r.json()["tinted"] is True


def test_bad_cached_checkpoint_is_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "models_dir", lambda: None)
    monkeypatch.setattr(em, "_cache_dir", lambda: tmp_path)
    (tmp_path / em.FILE).write_bytes(b"truncated")
    with pytest.raises(Exception) as e:
        em.apollo_path()
    assert getattr(e.value, "code", None) == "model_missing"
    assert not (tmp_path / em.FILE).exists()  # the next try downloads again


@pytest.mark.parametrize("module,name", [("torch.hub", "load"), ("torch.utils.cpp_extension", "load_inline"),
                                         ("numpy", "load"), ("builtins", "eval"), ("os", "system")])
def test_restricted_unpickler_blocks_callables(module, name):
    import io

    u = em._Restricted(io.BytesIO(b""))
    with pytest.raises(pickle.UnpicklingError):
        u.find_class(module, name)


def test_restricted_unpickler_allows_tensor_rebuild():
    import io

    u = em._Restricted(io.BytesIO(b""))
    assert u.find_class("torch._utils", "_rebuild_tensor_v2")
    assert u.find_class("collections", "OrderedDict")


def test_duration_of_a_webm(tmp_path):
    from djengine.stems.runner import _duration

    p = tmp_path / "a.webm"
    subprocess.run([find_tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "sine=d=3", "-c:a", "libopus", "-y", str(p)], check=True)
    assert abs((_duration(p) or 0) - 3.0) < 0.1


async def test_dedup_ignores_case_and_separators(svc, song):  # noqa: F811
    a = submit_enhance(svc, song, "copy", "same")
    b = submit_enhance(svc, Path(str(song).upper().replace("\\", "/")), "copy", "same")
    assert a.id == b.id
    await _wait(svc, a)


async def test_access_denied_backup_folder_is_a_disk_error(svc, song, monkeypatch):  # noqa: F811
    real = os.replace

    def denied(a, b):
        if Path(a) == song:
            e = PermissionError(13, "access denied")
            e.winerror = 5
            raise e
        return real(a, b)

    monkeypatch.setattr(er.os, "replace", denied)
    job = await _run(svc, song, "replace", "same")
    assert job.status == "failed" and job.error["code"] == "disk"


def test_ogg_with_opus_stays_opus():
    assert target_codec(Path("a.ogg"), "same", ("opus", None)) == ("ogg", ["-c:a", "libopus", "-b:a", "256k"])
    assert target_codec(Path("a.ogg"), "same", ("vorbis", None)) == ("ogg", ["-c:a", "libvorbis", "-q:a", "10"])


async def test_title_card_with_a_quote_in_the_temp_path(tmp_path, monkeypatch):
    from djengine.export.video import make_video_export_runner
    from djengine.library import TrackRecord

    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "0")
    s = build_services(AppPaths.from_root(tmp_path / "O'Neil" / "data"), fake=True)
    s.settings.music_dir = str(tmp_path / "O'Neil" / "music")
    p = Path(s.settings.music_dir) / "Bare.wav"
    p.parent.mkdir(parents=True)
    subprocess.run([find_tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "sine=d=2", "-y", str(p)], check=True)
    s.library.add_track(TrackRecord(None, None, "Bare", "It's me", "", 2, None, str(p), "wav", None, None, ""))
    t = s.library.track_by_path(str(p))
    job = s.jobs.submit("video_export", "t", make_video_export_runner(s, [t.id], "720", None))
    while s.jobs.get(job.id).status not in FINAL:
        await asyncio.sleep(0.05)
    j = s.jobs.get(job.id)
    assert j.status == "done" and j.result["failed"] == [] and len(j.result["exported"]) == 1, j.result


def test_preview_clips_are_removed_on_close(svc):  # noqa: F811
    from fastapi.testclient import TestClient

    clip = svc.paths.tmp_dir / "preview" / "x.wav"
    with TestClient(create_app(svc, token="t")):
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_bytes(b"x")
    assert not clip.exists()
