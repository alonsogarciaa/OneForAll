import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from djengine.analysis.store import AnalysisRecord, file_stamp, now_iso
from djengine.discover import quick
from djengine.discover.fit import fit
from djengine.discover.quick import QuickCache, lookup, make_quick_runner
from djengine.library import TrackRecord
from djengine.server import create_app
from tests.export.test_model import svc  # noqa: F401  (fixture)

FINAL = ("done", "failed", "cancelled")


@pytest.mark.parametrize("ref,cand,expected", [
    ((128, "8A"), (128, "8A"), "encaja"), ((128, "8A"), (64, "9A"), "encaja"), ((128, "8A"), (140, "8A"), "cerca"),
    ((128, "8A"), (128, "3B"), "cerca"), ((128, "8A"), (100, "3B"), None), ((None, None), (128, "8A"), None),
    ((128, None), (121, None), "cerca"), ((128, "8A"), (None, None), None), ((128, "8A"), (256, "8B"), "encaja")])
def test_fit(ref, cand, expected):
    assert fit(*ref, *cand) == expected


@pytest.fixture
def counted(svc, monkeypatch):  # noqa: F811
    calls = []
    real = svc.clip_downloader

    async def clip(ctx, url, start_s, seconds=60):
        calls.append(url)
        return await real(ctx, url, start_s, seconds)

    svc.clip_downloader = clip
    events = []

    async def bc(e):
        events.append(e)

    monkeypatch.setattr(svc.hub, "broadcast", bc)
    return calls, events


async def _run(svc, ids):  # noqa: F811
    job = svc.jobs.submit("quick_analysis", "t", make_quick_runner(svc, ids, [200] * len(ids)))
    while svc.jobs.get(job.id).status not in FINAL:
        await asyncio.sleep(0.02)
    return svc.jobs.get(job.id)


async def test_job_emits_results_and_caches(svc, counted):  # noqa: F811
    calls, events = counted
    j = await _run(svc, ["a1", "b8"])
    assert j.status == "done", j.error
    res = {e["video_id"]: e for e in events if e["type"] == "quick.result"}
    assert abs(res["a1"]["bpm"] - 120) <= 1 and abs(res["b8"]["bpm"] - 128) <= 1 and not res["a1"]["failed"]
    assert len(calls) == 2
    await _run(svc, ["a1", "b8"])
    assert len(calls) == 2  # cached: nothing downloaded again
    known = lookup(svc, ["a1", "zz"])
    assert set(known) == {"a1"} and abs(known["a1"]["bpm"] - 120) <= 1


async def test_failure_is_cached_for_24_hours(svc, counted, monkeypatch):  # noqa: F811
    calls, events = counted
    await _run(svc, ["private1"])
    assert [e["failed"] for e in events if e["type"] == "quick.result"] == [True]
    await _run(svc, ["private1"])
    assert len(calls) == 1
    later = datetime.now(timezone.utc) + timedelta(hours=25)
    monkeypatch.setattr(quick, "_now", lambda: later)
    await _run(svc, ["private1"])
    assert len(calls) == 2


async def test_library_track_analysis_is_reused(svc, counted, tmp_path):  # noqa: F811
    calls, events = counted
    p = tmp_path / "lib.wav"
    p.write_bytes(b"x")
    svc.library.add_track(TrackRecord(None, "inlib", "T", "A", "", 200, None, str(p), "wav", None, None, ""))
    size, mtime = file_stamp(p)
    svc.analysis.save(AnalysisRecord(path=str(p), size=size, mtime=mtime, bpm=99.0, bpm_confidence=1, bpm_source="auto",
                                     tonic="A", mode="minor", camelot="8A", key_confidence=1, lufs=None, peak_db=None,
                                     version=2, created_at=now_iso()), {"beats": []})
    await _run(svc, ["inlib"])
    assert calls == [] and lookup(svc, ["inlib"])["inlib"] == {"bpm": 99.0, "camelot": "8A", "failed": False}
    assert [e["bpm"] for e in events if e["type"] == "quick.result"] == [99.0]


async def test_cancel_keeps_finished_ones(svc, counted, monkeypatch):  # noqa: F811
    calls, events = counted
    slow = svc.clip_downloader

    async def clip(ctx, url, start_s, seconds=60):
        await asyncio.sleep(0.3)
        return await slow(ctx, url, start_s, seconds)

    svc.clip_downloader = clip
    ids = [f"c{i}" for i in range(8)]
    job = svc.jobs.submit("quick_analysis", "t", make_quick_runner(svc, ids, [200] * 8))
    while len([e for e in events if e["type"] == "quick.result"]) < 2:
        await asyncio.sleep(0.02)
    await svc.jobs.cancel(job.id)
    while svc.jobs.get(job.id).status not in FINAL:
        await asyncio.sleep(0.02)
    assert svc.jobs.get(job.id).status == "cancelled"
    done = set(lookup(svc, ids))
    assert len(done) >= 2
    before = len(calls)
    svc.clip_downloader = slow
    await _run(svc, ids)
    assert len(calls) - before == len(ids) - len(done)


def test_cache_table(tmp_path):
    c = QuickCache(tmp_path / "x.db")
    c.put("v", {"bpm": 120.0, "camelot": "8A"})
    c.put("w", None)
    assert c.get("v") == {"bpm": 120.0, "camelot": "8A", "failed": False}
    assert c.get("w") == {"bpm": None, "camelot": None, "failed": True}
    assert c.get("nope") is None


def test_api(svc):  # noqa: F811
    with TestClient(create_app(svc, token="t")) as c:
        r = c.post("/jobs", json={"type": "quick_analysis", "video_ids": ["a1"], "durations": [200]}, headers={"X-Token": "t"})
        assert r.status_code == 200 and r.json()["job"]["type"] == "quick_analysis"
        assert c.post("/jobs", json={"type": "quick_analysis", "video_ids": []}, headers={"X-Token": "t"}).status_code == 422
