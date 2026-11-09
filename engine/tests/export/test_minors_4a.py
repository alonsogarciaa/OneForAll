"""Phase 4a review minors: exporters, history, grid reset on v1 analyses, NaN sections."""
import asyncio
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from djengine.analysis.store import AnalysisRecord, file_stamp, now_iso
from djengine.export import virtualdj as vdj
from djengine.export.model import Cue, ExportTrack
from djengine.export.rekordbox import rekordbox_xml
from djengine.server import create_app
from tests.export.test_job import FINAL, H, add, run, svc, wav  # noqa: F401


def _t(path, title="T"):
    return ExportTrack(1, str(path), title, "Art", "Alb", 10.0, 100, 128.0, "Am", 0.5, [Cue(0.5, "Intro", (1, 2, 3), 0)])


def test_virtualdj_is_all_or_nothing_across_drives(tmp_path, monkeypatch):
    good, bad = tmp_path / "C" / "VirtualDJ", tmp_path / "E" / "VirtualDJ"
    good.mkdir(parents=True)
    bad.mkdir(parents=True)
    (bad / "database.xml").write_text("<not xml", encoding="utf-8")
    monkeypatch.setattr(vdj, "virtualdj_running", lambda: False)
    monkeypatch.setattr(vdj, "database_for", lambda p: (good if "C" in Path(p).parts[-2] else bad) / "database.xml")
    with pytest.raises(Exception):
        vdj.write_virtualdj([_t(tmp_path / "C" / "a.mp3"), _t(tmp_path / "E" / "b.mp3")])
    assert not (good / "database.xml").exists()  # nothing written when one database is unreadable


def test_virtualdj_reads_a_latin1_database(tmp_path, monkeypatch):
    d = tmp_path / "VirtualDJ"
    d.mkdir()
    (d / "database.xml").write_bytes('<?xml version="1.0" encoding="ISO-8859-1"?>\n<VirtualDJ_Database Version="8.5">'
                                     '<Song FilePath="D:/Canción.mp3" FileSize="1"/></VirtualDJ_Database>'.encode("latin-1"))
    monkeypatch.setattr(vdj, "virtualdj_running", lambda: False)
    monkeypatch.setattr(vdj, "database_for", lambda p: d / "database.xml")
    vdj.write_virtualdj([_t(tmp_path / "a.mp3")])
    paths = [s.get("FilePath") for s in ET.parse(d / "database.xml").getroot().findall("Song")]
    assert "D:/Canción.mp3" in paths and str(tmp_path / "a.mp3") in paths


def test_virtualdj_keeps_only_the_last_five_backups(tmp_path, monkeypatch):
    d = tmp_path / "VirtualDJ"
    d.mkdir()
    (d / "database.xml").write_text('<VirtualDJ_Database Version="8.5"/>', encoding="utf-8")
    for i in range(7):
        (d / f"database.xml.bak-20260101-00000{i}").write_text("old", encoding="utf-8")
    monkeypatch.setattr(vdj, "virtualdj_running", lambda: False)
    monkeypatch.setattr(vdj, "database_for", lambda p: d / "database.xml")
    vdj.write_virtualdj([_t(tmp_path / "a.mp3")])
    backups = sorted(p.name for p in d.glob("database.xml.bak-*"))
    assert len(backups) == 5 and "database.xml.bak-20260101-000000" not in backups


def test_control_characters_never_reach_the_xml(tmp_path):
    t = _t(tmp_path / "a.mp3", title="Bad\x01Title\x1f\tok")
    for xml in (rekordbox_xml([t], [("Lista\x02", [1])]), vdj.merge_database(None, [t])):
        root = ET.fromstring(xml.encode("utf-8"))  # parses: no invalid XML characters
        titles = [e.get("Name") or e.get("Title") for e in root.iter() if e.get("Name") or e.get("Title")]
        assert "BadTitle\tok" in titles


def test_rekordbox_out_must_be_our_file(svc, tmp_path):  # noqa: F811
    with TestClient(create_app(svc, token="t")) as c:
        bad = c.post("/jobs", json={"type": "dj_export", "target": "rekordbox", "out": str(tmp_path / "rekordbox.xml")}, headers=H)
        assert bad.status_code == 422
        ok = c.post("/jobs", json={"type": "dj_export", "target": "rekordbox",
                                   "out": str(tmp_path / "OneForAll rekordbox.xml")}, headers=H)
        assert ok.status_code == 200


async def test_dj_export_unexpected_failure_is_in_the_history(svc, tmp_path, monkeypatch):  # noqa: F811
    from djengine.export import job as jb

    svc.settings.music_dir = str(tmp_path / "music")
    add(svc, wav(tmp_path, "a.wav"))

    def boom(*a, **k):
        raise OSError("disk gone")

    monkeypatch.setattr(jb, "write_rekordbox", boom)
    j = await run(svc, "rekordbox")
    assert j.status == "failed"
    assert svc.library.list_history()[0].status == "failed"


async def test_retempo_failure_is_in_the_history(svc, tmp_path):  # noqa: F811
    from djengine.prep.retempo import make_retempo_runner

    p = wav(tmp_path, "s.wav")
    add(svc, p)
    p.write_bytes(b"not audio any more")  # ffmpeg will fail
    size, mtime = file_stamp(p)
    rec = svc.analysis.get_any(p)
    svc.analysis.save(AnalysisRecord(**{**rec.__dict__, "size": size, "mtime": mtime}), svc.analysis.read_sidecar(p))
    job = svc.jobs.submit("retempo", "t", make_retempo_runner(svc, p, 120.0, 0, None))
    while svc.jobs.get(job.id).status not in FINAL:
        await asyncio.sleep(0.02)
    assert svc.jobs.get(job.id).status == "failed"
    h = svc.library.list_history()[0]
    assert (h.action, h.status) == ("retempo", "failed")


def test_grid_reset_on_a_v1_analysis_goes_back_to_the_detected_grid(svc, tmp_path):  # noqa: F811
    p = wav(tmp_path, "v1.wav")
    size, mtime = file_stamp(p)
    svc.analysis.save(AnalysisRecord(path=str(p), size=size, mtime=mtime, bpm=120.0, bpm_confidence=0.9, bpm_source="auto",
                                     tonic="A", mode="minor", camelot="8A", key_confidence=0.9, lufs=-9.0, peak_db=-1.0,
                                     version=1, created_at=now_iso()),
                      {"beats": [0.5, 1.0, 1.5], "waveform": {}, "duration": 10.0})
    with TestClient(create_app(svc, token="t")) as c:
        assert c.put("/analysis/grid", json={"path": str(p), "shift_beats": 1}, headers=H).status_code == 200
        g = c.put("/analysis/grid", json={"path": str(p), "reset": True}, headers=H).json()["grid"]
        assert g["anchor"] == 0.5 and g["bpm"] == 120.0 and g["source"] == "auto"


def test_sections_reject_nan(svc, tmp_path):  # noqa: F811
    p = wav(tmp_path, "s.wav")
    add(svc, p)
    with TestClient(create_app(svc, token="t")) as c:
        body = {"path": str(p), "sections": [{"start": 0, "end": "NaN", "label": "Intro"}]}
        r = c.put("/analysis/sections", content=__import__("json").dumps(body).replace('"NaN"', "NaN"),
                  headers={**H, "Content-Type": "application/json"})
        assert r.status_code == 422
