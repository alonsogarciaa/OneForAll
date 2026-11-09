import asyncio
import subprocess
import time
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from djengine.analysis.store import AnalysisRecord, file_stamp, now_iso
from djengine.export import virtualdj as vdj
from djengine.export.job import make_dj_export_runner
from djengine.export import serato
from djengine.prep.sections import Section
from djengine.server import create_app
from djengine.tools import find_tool
from tests.export.test_model import add, svc  # noqa: F401

H = {"X-Token": "t"}
FINAL = ("done", "failed", "cancelled")


def wav(tmp_path, name):
    p = tmp_path / name
    sf.write(p, np.zeros((44100, 2), dtype=np.float32), 44100)
    return p


def mp3(tmp_path, name):
    w = wav(tmp_path, name + ".src.wav")
    p = tmp_path / name
    subprocess.run([find_tool("ffmpeg"), "-v", "error", "-y", "-i", str(w), "-c:a", "libmp3lame", str(p)], check=True)
    return p


async def run(svc, target, ids=None, out=None):
    job = svc.jobs.submit("dj_export", target, make_dj_export_runner(svc, target, ids, out))
    while svc.jobs.get(job.id).status not in FINAL:
        await asyncio.sleep(0.02)
    return svc.jobs.get(job.id)


async def test_rekordbox_job_writes_file_with_playlists(svc, tmp_path):  # noqa: F811
    svc.settings.music_dir = str(tmp_path / "music")
    a = add(svc, wav(tmp_path, "a.wav"), sections=[Section(0, 10, "Intro")])
    b = add(svc, wav(tmp_path, "b.wav"))
    pl = svc.library.add_playlist("PL", "Perreo", str(tmp_path))
    svc.library.add_playlist_track(pl, a, 0)
    j = await run(svc, "rekordbox")
    assert j.status == "done", j.error
    assert j.result["exported"] == 2 and j.result["skipped"] == []
    out = tmp_path / "music" / "OneForAll rekordbox.xml"
    assert j.result["file"] == str(out)
    root = ET.parse(out).getroot()
    assert len(root.findall("COLLECTION/TRACK")) == 2
    assert [t.get("Key") for t in root.find("PLAYLISTS/NODE/NODE/NODE").findall("TRACK")] == [str(a)]
    assert b
    h = svc.library.list_history()
    assert h[0].action == "export" and h[0].status == "done"


async def test_serato_job_skips_wav_and_counts(svc, tmp_path):  # noqa: F811
    add(svc, wav(tmp_path, "a.wav"))
    m = mp3(tmp_path, "b.mp3")
    add(svc, m, sections=[Section(0, 10, "Intro")])
    j = await run(svc, "serato")
    assert j.status == "done", j.error
    assert j.result["exported"] == 1 and j.result["skipped"] == [{"title": "a", "reason": "Formato no compatible con Serato"}]
    assert serato.read_serato(m)["grid"] == (0.5, 128.0)


async def test_virtualdj_job_busy_fails_without_writing(svc, tmp_path, monkeypatch):  # noqa: F811
    add(svc, wav(tmp_path, "a.wav"))
    monkeypatch.setattr(vdj, "virtualdj_running", lambda: True)
    db = tmp_path / "VirtualDJ" / "database.xml"
    monkeypatch.setattr(vdj, "database_for", lambda p: db)
    j = await run(svc, "virtualdj")
    assert j.status == "failed" and j.error["message"] == "Cierra VirtualDJ para exportar" and not db.exists()


async def test_virtualdj_job_writes(svc, tmp_path, monkeypatch):  # noqa: F811
    add(svc, wav(tmp_path, "a.wav"))
    monkeypatch.setattr(vdj, "virtualdj_running", lambda: False)
    db = tmp_path / "VirtualDJ" / "database.xml"
    db.parent.mkdir()
    monkeypatch.setattr(vdj, "database_for", lambda p: db)
    j = await run(svc, "virtualdj")
    assert j.status == "done" and j.result["exported"] == 1 and db.exists()


async def test_v1_analysis_exports_grid_without_cues(svc, tmp_path):  # noqa: F811
    p = wav(tmp_path, "old.wav")
    svc.library.add_track(__import__("djengine.library", fromlist=["TrackRecord"]).TrackRecord(
        None, None, "old", "A", "", 1, None, str(p), "wav", None, None, ""))
    size, mtime = file_stamp(p)
    svc.analysis.save(AnalysisRecord(path=str(p), size=size, mtime=mtime, bpm=120.0, bpm_confidence=0.9,
                                     bpm_source="auto", tonic="A", mode="minor", camelot="8A", key_confidence=0.8,
                                     lufs=-9.0, peak_db=-1.0, version=1, created_at=now_iso()),
                      {"beats": [0.25, 0.75], "waveform": {}, "duration": 1.0})
    out = tmp_path / "rb.xml"
    j = await run(svc, "rekordbox", out=str(out))
    t = ET.parse(out).getroot().find("COLLECTION/TRACK")
    assert j.status == "done" and t.find("TEMPO").get("Inizio") == "0.250" and t.findall("POSITION_MARK") == []


async def test_unanalysed_skipped(svc, tmp_path):  # noqa: F811
    add(svc, wav(tmp_path, "a.wav"), analysed=False)
    j = await run(svc, "rekordbox", out=str(tmp_path / "rb.xml"))
    assert j.result["exported"] == 0 and j.result["skipped"] == [{"title": "a", "reason": "Sin analizar"}]


def test_api_422_on_bad_target(svc, tmp_path):  # noqa: F811
    with TestClient(create_app(svc, token="t")) as c:
        assert c.post("/jobs", json={"type": "dj_export", "target": "traktor"}, headers=H).status_code == 422
        assert c.post("/jobs", json={"type": "dj_export", "target": "rekordbox", "out": str(tmp_path / "x.txt")},
                      headers=H).status_code == 422
        r = c.post("/jobs", json={"type": "dj_export", "target": "rekordbox", "out": str(tmp_path / "OneForAll rekordbox.xml")}, headers=H)
        assert r.status_code == 200
        jid = r.json()["job"]["id"]
        end = time.time() + 10
        while time.time() < end and next(j for j in c.get("/jobs", headers=H).json() if j["id"] == jid)["status"] not in FINAL:
            time.sleep(0.05)
        assert (tmp_path / "x.xml").exists()
