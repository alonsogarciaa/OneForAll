"""Regression tests for the phase 3a final review findings."""
import asyncio
import errno
import time

import numpy as np
import pytest
import soundfile as sf

from djengine.errors import UserError
from djengine.library import TrackRecord
from djengine.stems import runner as runner_mod
from djengine.stems import separate as sep_mod
from djengine.stems.runner import make_stems_runner
from djengine.tags import TrackMeta, write_tags
from tests.stems.test_runner import folder, run, song, svc  # noqa: F401  (fixtures)

SR = 44100


def test_own_tag_writes_keep_stems_valid(svc, ctx, song):  # noqa: F811
    from djengine.analysis import runner as ar

    run(svc, ctx, song, ["vocals"])
    assert svc.stems.get(song)
    ar_ctx = type(ctx)(ctx.tmp_dir.parent / "an")
    asyncio.run(ar.make_analysis_runner(svc, song)(ar_ctx))  # writes BPM/key tags into the source
    assert set(svc.stems.get(song)) == {"vocals"}


def test_different_sources_never_share_a_folder(svc, ctx, song, tmp_path):  # noqa: F811
    run(svc, ctx, song, ["vocals"])
    other = tmp_path / "other.wav"
    sf.write(other, np.zeros((SR, 2), dtype=np.float32), SR)
    write_tags(other, TrackMeta("LA GRACIOSA", "Quevedo"), None)  # same artist/title, different file
    r = run(svc, ctx, other, ["vocals"])
    assert r["folder"] != str(folder(svc))
    assert r["folder"].endswith("Quevedo - LA GRACIOSA (1)")
    assert svc.stems.get(song)["vocals"].parent == folder(svc)


def test_too_long_audio_is_refused_before_any_work(svc, ctx, song, monkeypatch):  # noqa: F811
    monkeypatch.setattr(runner_mod, "MAX_SECONDS", 1)
    with pytest.raises(UserError) as e:
        run(svc, ctx, song, ["vocals"])
    assert e.value.code == "too_long"


def test_failed_cross_drive_copy_leaves_no_partial_file(svc, ctx, song, monkeypatch):  # noqa: F811
    import djengine.pipelines as p

    def exdev(*a, **k):
        raise OSError(errno.EXDEV, "cross-device")

    def full(src, dst, *a, **k):
        with open(dst, "wb") as f:
            f.write(b"partial")
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(p.os, "replace", exdev)
    monkeypatch.setattr(p.shutil, "copy2", full)
    with pytest.raises(UserError) as e:
        run(svc, ctx, song, ["vocals"])
    assert e.value.code == "disk"
    f = folder(svc)
    assert not f.exists() or [x for x in f.iterdir() if x.suffix == ".wav"] == []


async def test_cancel_waits_for_the_worker_thread(svc, song, monkeypatch):  # noqa: F811
    finished = []

    def stubborn(self, audio, sr, progress, cancelled):
        time.sleep(1.5)  # e.g. karaoke or encoding: does not check cancellation
        finished.append(time.monotonic())
        return {s: audio for s in sep_mod.STEMS}

    monkeypatch.setattr(sep_mod.FakeSeparator, "separate", stubborn)
    job = svc.jobs.submit("stems", "t", make_stems_runner(svc, song, ["vocals"]))
    while svc.jobs.get(job.id).stage != "separating":  # cancel while the stubborn step runs, however slow decoding is
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.2)
    assert await svc.jobs.cancel(job.id)
    while svc.jobs.get(job.id).status not in ("done", "failed", "cancelled"):
        await asyncio.sleep(0.05)
    assert finished, "job was reported cancelled while its thread was still running"
    assert not (svc.paths.tmp_dir / job.id).exists()
