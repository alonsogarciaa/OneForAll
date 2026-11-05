"""Deferred minor findings, group B (jobs, files, processes)."""
import asyncio
import errno
import os
import subprocess
import sys
import threading
import time

import psutil
import pytest

from djengine import pipelines
from djengine.errors import UserError
from djengine.jobs import JobManager
from djengine.naming import unique_path
from tests.test_jobs import FINAL, wait_done


@pytest.fixture
def mgr(tmp_path):
    async def emit(e):
        pass

    return JobManager(tmp_path / "tmp", emit, {"download": 1})


def _blocker(started, gate):
    async def r(ctx):
        started.append(1)
        await gate.wait()
        return {}

    return r


async def test_same_concurrency_reset_does_not_open_extra_slot(mgr):
    started, gate = [], asyncio.Event()
    a = mgr.submit("download", "a", _blocker(started, gate))
    await asyncio.sleep(0.05)
    mgr.set_concurrency("download", 1)
    b = mgr.submit("download", "b", _blocker(started, gate))
    await asyncio.sleep(0.1)
    assert len(started) == 1  # b waits for a's slot
    gate.set()
    await wait_done(mgr, a.id)
    await wait_done(mgr, b.id)
    assert len(started) == 2


async def test_raising_concurrency_starts_waiting_jobs(mgr):
    started, gate = [], asyncio.Event()
    jobs = [mgr.submit("download", str(i), _blocker(started, gate)) for i in range(3)]
    await asyncio.sleep(0.05)
    assert len(started) == 1
    mgr.set_concurrency("download", 3)
    await asyncio.sleep(0.1)
    assert len(started) == 3
    gate.set()
    for j in jobs:
        await wait_done(mgr, j.id)


async def test_cancelled_waiting_job_frees_nothing(mgr):
    started, gate = [], asyncio.Event()
    a = mgr.submit("download", "a", _blocker(started, gate))
    b = mgr.submit("download", "b", _blocker(started, gate))
    await asyncio.sleep(0.05)
    await mgr.cancel(b.id)
    await wait_done(mgr, b.id)
    c = mgr.submit("download", "c", _blocker(started, gate))
    await asyncio.sleep(0.1)
    assert len(started) == 1  # a still holds the only slot
    gate.set()
    await wait_done(mgr, a.id)
    await wait_done(mgr, c.id)


async def test_cancelled_analysis_waits_for_its_thread(tmp_path, monkeypatch):
    from djengine.analysis import runner as ar

    finished = []

    def slow(path, ctx, lo, hi):
        time.sleep(0.3)  # a blocking step that cannot notice the cancel
        finished.append(1)
        ctx.check_cancelled()

    monkeypatch.setattr(ar, "_analyse", slow)
    song = tmp_path / "s.wav"
    song.write_bytes(b"x")

    class Svc:
        analysis = None

    async def emit(e):
        pass

    m = JobManager(tmp_path / "tmp", emit, {"analysis": 1})
    job = m.submit("analysis", "s", ar.make_analysis_runner(type("S", (), {"analysis": _NoStore(), "settings": _S()})(), song))
    await asyncio.sleep(0.05)
    await m.cancel(job.id)
    await wait_done(m, job.id)
    assert m.get(job.id).status == "cancelled" and finished == [1]


class _NoStore:
    def get(self, p):
        return None

    def get_any(self, p):
        return None


class _S:
    bpm_min, bpm_max = 70, 180


def test_cross_drive_copy_uses_sweepable_part_name(tmp_path, monkeypatch):
    src = tmp_path / "a.mp3"
    src.write_bytes(b"data")
    final = tmp_path / "out" / "Song.mp3"
    final.parent.mkdir()
    seen = []
    real_replace = os.replace

    def fake_replace(a, b):
        if str(a) == str(src):
            raise OSError(errno.EXDEV, "cross-device")
        seen.append(os.path.basename(str(a)))
        return real_replace(a, b)

    monkeypatch.setattr(pipelines.os, "replace", fake_replace)
    pipelines._commit(src, final)
    assert final.read_bytes() == b"data"
    assert seen and seen[0].startswith("~oneforall-") and seen[0].endswith(".part")


def test_sweep_removes_leftover_parts(tmp_path):
    (tmp_path / "Artist").mkdir()
    left = tmp_path / "Artist" / "~oneforall-1234.part"
    left.write_bytes(b"x")
    keep = tmp_path / "Artist" / "song.part"
    keep.write_bytes(b"x")
    pipelines.sweep_parts([tmp_path, tmp_path / "missing"])
    assert not left.exists() and keep.exists()


def test_unique_path_stays_under_max_path(tmp_path):
    deep = tmp_path / ("d" * 120)
    p = unique_path(deep, "x" * 180, "flac")
    assert len(str(p)) <= 250 and p.suffix == ".flac" and p.stem.startswith("xxx")


def test_ffmpeg_disk_full_maps_to_disk():
    from djengine.convert import ffmpeg_error

    assert ffmpeg_error("av_interleaved_write_frame(): No space left on device").code == "disk"
    assert ffmpeg_error("Invalid data found").code == "internal"


async def test_convert_missing_source_goes_to_history(tmp_path):
    from djengine.convert import ConvertOptions
    from djengine.library import Library

    lib = Library(tmp_path / "db")
    svc = type("S", (), {"library": lib})()
    run = pipelines.make_convert_runner(svc, tmp_path / "gone.wav", ConvertOptions(format="mp3"))
    with pytest.raises(UserError):
        await run(type("C", (), {"tmp_dir": tmp_path})())
    h = lib.list_history()
    assert h and h[0].action == "convert" and h[0].status == "failed"


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Objects")
def test_children_die_with_engine():
    code = (
        "import subprocess, sys, time\n"
        "from djengine.__main__ import bind_children_to_engine\n"
        "assert bind_children_to_engine()\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print(p.pid, flush=True)\n"
        "time.sleep(60)\n"
    )
    parent = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    child = int(parent.stdout.readline())
    assert psutil.pid_exists(child)
    parent.kill()  # hard crash: no cleanup code runs
    parent.wait()
    deadline = time.time() + 5
    while psutil.pid_exists(child) and time.time() < deadline:
        time.sleep(0.1)
    assert not psutil.pid_exists(child)
