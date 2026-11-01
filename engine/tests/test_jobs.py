import asyncio
import sys

import psutil
import pytest

from djengine.errors import UserError
from djengine.jobs import JobManager

FINAL = {"done", "failed", "cancelled"}


@pytest.fixture
def tmp_root(tmp_path):
    d = tmp_path / "tmp"
    d.mkdir()
    return d


@pytest.fixture
def events():
    return []


@pytest.fixture
def mgr(tmp_root, events):
    async def emit(e):
        events.append(e)

    return JobManager(tmp_root, emit, {"download": 3, "convert": 2})


async def wait_done(mgr, job_id, timeout=10):
    async def loop():
        while mgr.get(job_id).status not in FINAL:
            await asyncio.sleep(0.02)

    await asyncio.wait_for(loop(), timeout)


async def test_runs_and_cleans_tmp(mgr, tmp_root, events):
    async def r(ctx):
        (ctx.tmp_dir / "x").write_text("1")
        ctx.report("downloading", 50)
        return {"ok": 1}

    job = mgr.submit("download", "t", r)
    await wait_done(mgr, job.id)
    j = mgr.get(job.id)
    assert j.status == "done" and j.result == {"ok": 1} and j.pct == 100
    assert not (tmp_root / job.id).exists()
    assert [e["type"] for e in events][-1] == "job.done"


async def test_cancel_kills_process_and_cleans(mgr, tmp_root):
    pids = []

    async def r(ctx):
        p = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(60)")
        pids.append(p.pid)
        ctx.register_process(p)
        (ctx.tmp_dir / "partial").write_text("x")
        await p.wait()
        ctx.check_cancelled()

    job = mgr.submit("download", "t", r)
    while not pids:
        await asyncio.sleep(0.05)
    assert await mgr.cancel(job.id) is True
    await wait_done(mgr, job.id)
    assert mgr.get(job.id).status == "cancelled"
    assert not (tmp_root / job.id).exists()
    await asyncio.sleep(0.3)
    assert not psutil.pid_exists(pids[0]) or psutil.Process(pids[0]).status() == psutil.STATUS_ZOMBIE


async def test_cancel_one_does_not_touch_others(mgr):
    gate = asyncio.Event()

    async def slow(ctx):
        await gate.wait()
        return {}

    a = mgr.submit("download", "a", slow)
    b = mgr.submit("download", "b", slow)
    await asyncio.sleep(0.05)
    assert await mgr.cancel(a.id)
    gate.set()
    await wait_done(mgr, b.id)
    await wait_done(mgr, a.id)
    assert mgr.get(a.id).status == "cancelled" and mgr.get(b.id).status == "done"


async def test_cancel_after_done_returns_false(mgr):
    async def r(ctx):
        return {}

    job = mgr.submit("download", "t", r)
    await wait_done(mgr, job.id)
    assert await mgr.cancel(job.id) is False
    assert await mgr.cancel("nope") is False
    assert mgr.get(job.id).status == "done"


async def test_concurrency_limit(mgr):
    gate = asyncio.Event()

    async def slow(ctx):
        await gate.wait()
        return {}

    jobs = [mgr.submit("convert", str(i), slow) for i in range(3)]
    await asyncio.sleep(0.1)
    assert [mgr.get(j.id).status for j in jobs] == ["running", "running", "queued"]
    assert mgr.active_count() == 3
    gate.set()
    for j in jobs:
        await wait_done(mgr, j.id)
    assert mgr.active_count() == 0


async def test_user_error_maps_code(mgr):
    async def r(ctx):
        raise UserError("offline", "Sin conexión")

    job = mgr.submit("download", "t", r)
    await wait_done(mgr, job.id)
    assert mgr.get(job.id).error == {"code": "offline", "message": "Sin conexión"}


async def test_unexpected_error_is_internal(mgr):
    async def r(ctx):
        raise RuntimeError("boom")

    job = mgr.submit("download", "t", r)
    await wait_done(mgr, job.id)
    assert mgr.get(job.id).error == {"code": "internal", "message": "Error inesperado"}


async def test_parent_cancel_cancels_children(mgr):
    gate = asyncio.Event()

    async def parent(ctx):
        await gate.wait()
        return {}

    async def slow(ctx):
        await gate.wait()
        return {}

    p = mgr.submit("playlist", "pl", parent)
    kids = [mgr.submit("download", str(i), slow, parent_id=p.id) for i in range(2)]
    await asyncio.sleep(0.05)
    assert mgr.get(p.id).children == [k.id for k in kids]
    assert mgr.active_count() == 2  # parents not counted
    assert await mgr.cancel(p.id)
    for k in kids:
        await wait_done(mgr, k.id)
        assert mgr.get(k.id).status == "cancelled"


def test_purge_orphans(tmp_root, events):
    (tmp_root / "stale").mkdir()
    (tmp_root / "stale" / "f").write_text("x")

    async def emit(e):
        pass

    assert JobManager(tmp_root, emit, {}).purge_orphans() == 1
    assert list(tmp_root.iterdir()) == []


async def test_cancel_during_final_emit_is_refused(tmp_root):
    release = asyncio.Event()

    async def emit(e):
        if e["type"] == "job.done":
            await release.wait()  # slow listener while the job is finishing

    mgr = JobManager(tmp_root, emit, {"download": 1})

    async def r(ctx):
        return {"ok": 1}

    job = mgr.submit("download", "t", r)
    await asyncio.sleep(0.1)  # runner done, final emit pending
    assert await mgr.cancel(job.id) is False
    release.set()
    await wait_done(mgr, job.id)
    assert mgr.get(job.id).status == "done" and mgr.active_count() == 0


def test_user_error_survives_pickle():
    import pickle

    e = pickle.loads(pickle.dumps(UserError("offline", "Sin conexión")))
    assert (e.code, e.message) == ("offline", "Sin conexión")
