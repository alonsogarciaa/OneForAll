import os
import time

import numpy as np
import pytest

from djengine.analysis.store import AnalysisRecord, AnalysisStore, file_stamp, now_iso
from djengine.prep.grid import Grid, beats, edit_grid, estimate_grid, grid_from_beats
from tests.test_api_analysis import H, env, final, wait  # noqa: F401

SR = 44100


def test_beats_from_anchor_includes_before():
    assert beats(Grid(1.0, 120), 3.0) == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]


def test_grid_from_beats_phase():
    g = grid_from_beats([0.26, 0.74, 1.25, 1.76], 120)
    assert abs(g.anchor - 0.25) < 0.01 and g.bpm == 120 and g.source == "auto"


def test_grid_from_no_beats():
    assert grid_from_beats([], 128).anchor == 0.0


def test_estimate_grid_finds_downbeat():
    y = np.zeros(SR * 8, dtype=np.float32)
    n = int(0.02 * SR)
    t = np.arange(n) / SR
    click = (np.sin(2 * np.pi * 1000 * t) * np.hanning(n)).astype(np.float32)
    m = int(0.12 * SR)
    thump = (np.sin(2 * np.pi * 60 * np.arange(m) / SR) * np.hanning(m)).astype(np.float32)
    detected = []
    for k in range(16):
        i = int(k * 0.5 * SR)
        y[i:i + n] += 0.3 * click
        if k % 4 == 2:  # bar "1" at 1.0 s, 3.0 s, ...
            y[i:i + m] += 0.9 * thump
        detected.append(k * 0.5)
    g = estimate_grid(y, SR, 120.0, detected)
    assert abs(g.anchor - 1.0) < 0.02


def test_edit_grid_ops():
    g = Grid(1.0, 120)
    assert abs(edit_grid(g, shift_ms=10).anchor - 1.01) < 1e-9
    assert abs(edit_grid(g, shift_beats=-1).anchor - 0.5) < 1e-9
    s = edit_grid(g, scale=2)
    assert s.bpm == 240 and s.anchor == 1.0
    assert edit_grid(g, anchor=2.5).anchor == 2.5 and edit_grid(g, bpm=126).bpm == 126
    assert all(e.source == "manual" for e in (s, edit_grid(g, shift_ms=1)))


def _v1(st, path, beats_list, bpm=120.0):
    size, mtime = file_stamp(path)
    st.save(AnalysisRecord(path=str(path), size=size, mtime=mtime, bpm=bpm, bpm_confidence=0.9, bpm_source="auto",
                           tonic="A", mode="minor", camelot="8A", key_confidence=0.9, lufs=-9.0, peak_db=-1.0,
                           version=1, created_at=now_iso()),
            {"beats": beats_list, "waveform": {}, "duration": 10.0})


def test_v1_sidecar_converted(tmp_path):
    st = AnalysisStore(tmp_path / "db", tmp_path / "side")
    song = tmp_path / "s.wav"
    song.write_bytes(b"x" * 10)
    _v1(st, song, [0.5, 1.0, 1.5])
    g = st.get_grid(song)
    assert g.anchor == 0.5 and g.bpm == 120.0  # spec: anchor = first beat of the old list


def test_save_grid_rewrites_beats(tmp_path):
    st = AnalysisStore(tmp_path / "db", tmp_path / "side")
    song = tmp_path / "s.wav"
    song.write_bytes(b"x" * 10)
    _v1(st, song, [0.25, 0.72, 1.19], bpm=128)
    st.save_grid(song, Grid(0.25, 120, "manual"))
    side = st.get_sidecar(song)
    b = side["beats"]
    assert b[0] == 0.25 and abs(b[1] - b[0] - 0.5) < 1e-6 and b[-1] < 10.0 and len(b) == 20
    assert side["grid"] == {"anchor": 0.25, "bpm": 120, "source": "manual", "meter": 4}


def _analysed(c, tmp_path, click_track_file):
    p = click_track_file(tmp_path / "c.wav")
    c.post("/jobs", json={"type": "analysis", "paths": [str(p)]}, headers=H)
    wait(c, lambda js: final(js, "analysis"))
    return p


def test_put_grid_api(env, click_track_file):  # noqa: F811
    c, svc, tmp = env
    p = _analysed(c, tmp, click_track_file)
    r = c.put("/analysis/grid", json={"path": str(p), "anchor": 2.0}, headers=H)
    assert r.status_code == 200 and r.json()["grid"]["anchor"] == 2.0 and r.json()["grid"]["source"] == "manual"
    side = c.get("/analysis", params={"path": str(p)}, headers=H).json()["sidecar"]
    assert 2.0 in side["beats"] and side["grid"]["anchor"] == 2.0
    r = c.put("/analysis/grid", json={"path": str(p), "bpm": 127.0}, headers=H).json()
    rec = c.get("/analysis", params={"path": str(p)}, headers=H).json()["record"]
    assert r["grid"]["bpm"] == 127.0 and rec["bpm"] == 127.0 and rec["bpm_source"] == "manual"
    auto = svc.analysis.get_sidecar(p)["grid_auto"]
    assert c.put("/analysis/grid", json={"path": str(p), "reset": True}, headers=H).json()["grid"] == auto
    st = p.stat()
    os.utime(p, (st.st_atime, st.st_mtime + 30))
    assert c.put("/analysis/grid", json={"path": str(p), "anchor": 1.0}, headers=H).status_code == 409


def test_reanalysis_keeps_manual_grid(env, click_track_file):  # noqa: F811
    c, svc, tmp = env
    p = _analysed(c, tmp, click_track_file)
    c.put("/analysis/grid", json={"path": str(p), "anchor": 1.234}, headers=H)
    c.post("/jobs", json={"type": "analysis", "paths": [str(p)], "force": True}, headers=H)
    time.sleep(0.2)
    wait(c, lambda js: len(final(js, "analysis")) >= 2)
    assert svc.analysis.get_grid(p).anchor == 1.234
