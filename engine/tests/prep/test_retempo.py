import asyncio
import time

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from djengine.analysis.camelot import camelot_shift
from djengine.analysis.store import AnalysisRecord, file_stamp, now_iso
from djengine.app_paths import AppPaths
from djengine.prep import retempo as rt
from djengine.prep.grid import Grid
from djengine.prep.retempo import make_retempo_runner, retempo_name
from djengine.prep.sections import Section
from djengine.server import build_services, create_app

SR = 44100
H = {"X-Token": "t"}
FINAL = ("done", "failed", "cancelled")


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "0")
    s = build_services(AppPaths.from_root(tmp_path / "data"), fake=True)
    s.settings.music_dir = str(tmp_path / "music")
    return s


@pytest.fixture
def song(tmp_path, svc):
    p = tmp_path / "music" / "Song.wav"
    p.parent.mkdir(parents=True)
    t = np.arange(SR * 4) / SR
    y = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sf.write(p, np.stack([y, y]).T, SR)
    size, mtime = file_stamp(p)
    svc.analysis.save(AnalysisRecord(path=str(p), size=size, mtime=mtime, bpm=120.0, bpm_confidence=0.9,
                                     bpm_source="auto", tonic="A", mode="minor", camelot="8A", key_confidence=0.8,
                                     lufs=-12.0, peak_db=-10.0, version=2, created_at=now_iso()),
                      {"beats": [], "waveform": {}, "duration": 4.0, "grid": Grid(1.0, 120.0, "manual").to_dict(),
                       "sections": [Section(0.0, 4.0, "Intro").to_dict()]})
    return p


async def _run(svc, path, bpm, semis, fmt=None):
    job = svc.jobs.submit("retempo", "t", make_retempo_runner(svc, path, bpm, semis, fmt))
    while svc.jobs.get(job.id).status not in FINAL:
        await asyncio.sleep(0.02)
    return svc.jobs.get(job.id)


def _dominant_hz(path):
    y, sr = sf.read(path)
    y = y[:, 0] if y.ndim > 1 else y
    seg = y[len(y) // 4: len(y) // 4 + sr]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    return np.argmax(spec) * sr / len(seg)


def test_retempo_name():
    assert retempo_name("Song", 128, 124, "8A", 2) == "Song (124 BPM, 10A)"
    assert retempo_name("Song", 128, 128, "8A", 1) == "Song (3A)"
    assert retempo_name("Song", 128, 124.25, None, 0) == "Song (124.2 BPM)"


def test_camelot_shift():
    assert camelot_shift("8A", 2) == "10A" and camelot_shift("8A", -1) == "1A" and camelot_shift("12B", 12) == "12B"


async def test_retempo_render_and_scaled_analysis(svc, song):
    j = await _run(svc, song, 60.0, 12)
    assert j.status == "done", j.error
    out = j.result["path"]
    assert out.endswith("Song (60 BPM, 8A).wav")
    assert abs(sf.info(out).duration - 8.0) < 0.1
    assert abs(_dominant_hz(out) - 880) / 880 < 0.01
    rec = svc.analysis.get(out)
    assert rec.bpm == 60.0 and rec.camelot == "8A" and rec.bpm_source == "manual" and rec.version == 2
    g = svc.analysis.get_grid(out)
    assert abs(g.anchor - 2.0) < 1e-6 and g.bpm == 60.0
    secs = svc.analysis.get_sections(out)
    assert [(s.start, s.end, s.label) for s in secs] == [(0.0, 8.0, "Intro")]
    assert svc.library.track_by_path(out) is not None


async def test_retempo_key_shift(svc, song):
    j = await _run(svc, song, 120.0, 2)
    rec = svc.analysis.get(j.result["path"])
    assert rec.camelot == "10A" and (rec.tonic, rec.mode) == ("B", "minor")


async def test_retempo_out_of_range(svc, song):
    j = await _run(svc, song, 240.0, 0)
    assert j.status == "failed" and j.error["code"] == "bad_request"


def test_retempo_api_rejects_out_of_range(svc, song):
    with TestClient(create_app(svc, token="t")) as c:
        r = c.post("/jobs", json={"type": "retempo", "path": str(song), "bpm": 30, "semis": 0}, headers=H)
        assert r.status_code == 422
        r = c.post("/jobs", json={"type": "retempo", "path": str(song), "bpm": 118, "semis": 13}, headers=H)
        assert r.status_code == 422


async def test_retempo_not_analysed(svc, tmp_path):
    other = tmp_path / "x.wav"
    sf.write(other, np.zeros((SR, 2), dtype=np.float32), SR)
    j = await _run(svc, other, 100.0, 0)
    assert j.status == "failed" and j.error["message"] == "Analiza primero"


async def test_retempo_name_collision(svc, song):
    a = await _run(svc, song, 100.0, 0)
    b = await _run(svc, song, 100.0, 0)
    assert a.result["path"].endswith("Song (100 BPM).wav") and b.result["path"].endswith("Song (100 BPM) (1).wav")


async def test_retempo_cancel_leaves_no_file(svc, song, monkeypatch):
    monkeypatch.setattr(rt, "_extra_args", lambda: ["-re"])
    job = svc.jobs.submit("retempo", "t", make_retempo_runner(svc, song, 60.0, 0, None))
    while svc.jobs.get(job.id).stage != "rendering":
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.3)
    assert await svc.jobs.cancel(job.id)
    while svc.jobs.get(job.id).status not in FINAL:
        await asyncio.sleep(0.02)
    assert svc.jobs.get(job.id).status == "cancelled"
    assert sorted(p.name for p in song.parent.iterdir()) == ["Song.wav"]
