import asyncio
import time

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from djengine.app_paths import AppPaths
from djengine.mixer import export as export_mod
from djengine.mixer.export import make_mix_export_runner
from djengine.mixer.state import MixState
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
    src = tmp_path / "song.wav"
    t = np.arange(SR * 3) / SR
    y = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sf.write(src, np.stack([y, y]).T, SR)
    folder = tmp_path / "music" / "Stems" / "A - B"
    folder.mkdir(parents=True)
    for name in ("vocals", "drums"):
        f = folder / f"{name}.wav"
        sf.write(f, np.stack([y, y]).T * (1 if name == "vocals" else 0), SR)
        svc.stems.add(src, name, f, "fake")
    return src


async def _run(svc, path, state, rng="full", fmt="wav16"):
    job = svc.jobs.submit("mix_export", "t", make_mix_export_runner(svc, path, state, rng, fmt))
    while svc.jobs.get(job.id).status not in FINAL:
        await asyncio.sleep(0.02)
    return svc.jobs.get(job.id)


def _dominant_hz(path):
    y, sr = sf.read(path)
    y = y[:, 0] if y.ndim > 1 else y
    seg = y[len(y) // 4: len(y) // 4 + sr]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    return np.argmax(spec) * sr / len(seg)


async def test_export_full_duration_and_pitch(svc, song):
    j = await _run(svc, song, MixState(rate=0.5, semis=12))
    assert j.status == "done", j.error
    out = j.result["file"]
    assert abs(sf.info(out).duration - 6.0) < 0.1
    assert abs(_dominant_hz(out) - 880) / 880 < 0.01


async def test_export_loop_only(svc, song):
    j = await _run(svc, song, MixState(loop={"start": 1, "end": 2}), "loop")
    assert j.status == "done", j.error
    assert abs(sf.info(j.result["file"]).duration - 1.0) < 0.05
    assert j.result["file"].split("\\")[-1].split("/")[-1].startswith("loop 00m01s-00m02s")


async def test_export_name_collision_uses_unique_path(svc, song):
    a = await _run(svc, song, MixState())
    b = await _run(svc, song, MixState())
    names = sorted(p.split("\\")[-1].split("/")[-1] for p in (a.result["file"], b.result["file"]))
    assert names == ["mix (1).wav", "mix.wav"]


async def test_export_cancel_leaves_no_file(svc, song, monkeypatch):
    state = MixState(rate=0.5)
    monkeypatch.setattr(export_mod, "_extra_args", lambda: ["-filter_threads", "1", "-re"])  # slow it down
    job = svc.jobs.submit("mix_export", "t", make_mix_export_runner(svc, song, state, "full", "wav16"))
    while svc.jobs.get(job.id).stage != "rendering":
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.3)
    assert await svc.jobs.cancel(job.id)
    while svc.jobs.get(job.id).status not in FINAL:
        await asyncio.sleep(0.02)
    folder = song.parent / "music" / "Stems" / "A - B"
    assert svc.jobs.get(job.id).status == "cancelled"
    assert sorted(p.name for p in folder.iterdir()) == ["drums.wav", "vocals.wav"]


async def test_export_missing_stems(svc, tmp_path):
    other = tmp_path / "other.wav"
    sf.write(other, np.zeros((SR, 2), dtype=np.float32), SR)
    j = await _run(svc, other, MixState())
    assert j.status == "failed" and j.error["message"] == "Faltan stems de esta canción"


async def test_export_over_12_minutes_refused(svc, song, monkeypatch):
    monkeypatch.setattr(export_mod, "_duration", lambda p: 13 * 60)
    j = await _run(svc, song, MixState())
    assert j.status == "failed" and j.error["code"] == "too_long"
    assert j.error["message"] == "Pista demasiado larga para el mezclador"


def test_export_history_and_drag(svc, song):
    with TestClient(create_app(svc, token="t")) as c:
        r = c.post("/jobs", json={"type": "mix_export", "path": str(song), "state": {"rate": 0.9}, "range": "full"}, headers=H)
        jid = r.json()["job"]["id"]
        end = time.time() + 30
        while time.time() < end:
            j = next(j for j in c.get("/jobs", headers=H).json() if j["id"] == jid)
            if j["status"] in FINAL:
                break
            time.sleep(0.05)
        assert j["status"] == "done", j
        f = j["result"]["file"]
        assert f.endswith("mix (0.90x).wav")
        assert c.post("/stems/check", json={"files": [f]}, headers=H).json() == {"stems": [f]}
        h = c.get("/history", headers=H).json()
        assert any(e["action"] == "export" and e["status"] == "done" for e in h)
        bad = {"type": "mix_export", "path": str(song), "state": {}, "range": "loop"}
        assert c.post("/jobs", json=bad, headers=H).status_code == 422
