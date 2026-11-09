import asyncio
import os
from pathlib import Path

import soundfile as sf

from djengine.app_paths import AppPaths
from djengine.enhance.runner import PREVIEW_S, make_preview_runner, preview_start
from djengine.server import _norm, build_services

from .test_runner import FINAL, _make, svc  # noqa: F401  (fixture)


def test_preview_start():
    side = {"sections": [{"start": 0, "end": 30, "label": "Intro"}, {"start": 30, "end": 60, "label": "Estribillo/Drop"},
                         {"start": 60, "end": 90, "label": "Estribillo/Drop"}]}
    assert preview_start(side, 200) == 30
    assert preview_start(None, 200) == 60
    assert preview_start({"sections": []}, 100) == 30
    assert preview_start(None, 10) == 0
    assert preview_start({"sections": [{"start": 190, "end": 200, "label": "Estribillo/Drop"}]}, 200) == 185


async def test_preview_job_writes_two_aligned_clips(svc, tmp_path):  # noqa: F811
    src = _make(tmp_path / "music" / "Long.wav", seconds=40)
    job = svc.jobs.submit("enhance_preview", "t", make_preview_runner(svc, src))
    while svc.jobs.get(job.id).status not in FINAL:
        await asyncio.sleep(0.02)
    j = svc.jobs.get(job.id)
    assert j.status == "done", j.error
    a, b = Path(j.result["original"]), Path(j.result["enhanced"])
    assert j.result["start"] == 12.0
    for p in (a, b):
        assert p.parent == svc.paths.tmp_dir / "preview"
        assert abs(sf.info(str(p)).duration - PREVIEW_S) < 0.05
        assert _norm(p) in svc.allowed_paths


def test_preview_dir_is_cleared_on_start(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "0")
    paths = AppPaths.from_root(tmp_path / "data")
    old = paths.tmp_dir / "preview" / "x.wav"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"x")
    build_services(paths, fake=True)
    assert not old.exists()
