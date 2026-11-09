import time

from djengine.analysis import config
from djengine.analysis.store import AnalysisRecord, file_stamp, now_iso
from tests.test_api_analysis import H, env, final, wait  # noqa: F401


def _analysed(c, tmp, click_track_file, name="c.wav"):
    p = click_track_file(tmp / name, seconds=40)
    c.post("/jobs", json={"type": "analysis", "paths": [str(p)]}, headers=H)
    wait(c, lambda js: final(js, "analysis"))
    return p


def test_version_is_2():
    assert config.ANALYSIS_VERSION == 2


def test_analysis_stores_sections(env, click_track_file):  # noqa: F811
    c, svc, tmp = env
    p = _analysed(c, tmp, click_track_file)
    side = c.get("/analysis", params={"path": str(p)}, headers=H).json()["sidecar"]
    assert isinstance(side["sections"], list) and side["needs_reanalysis"] is False
    assert side["sections_auto"] == side["sections"]


def test_v1_record_flags_reanalysis(env, tmp_path):  # noqa: F811
    c, svc, _ = env
    song = tmp_path / "old.wav"
    song.write_bytes(b"x" * 100)
    size, mtime = file_stamp(song)
    svc.analysis.save(AnalysisRecord(path=str(song), size=size, mtime=mtime, bpm=120.0, bpm_confidence=0.9,
                                     bpm_source="auto", tonic="A", mode="minor", camelot="8A", key_confidence=0.9,
                                     lufs=-9.0, peak_db=-1.0, version=1, created_at=now_iso()),
                      {"beats": [0.5, 1.0], "waveform": {}, "duration": 10.0})
    side = c.get("/analysis", params={"path": str(song)}, headers=H).json()["sidecar"]
    assert side["needs_reanalysis"] is True and side["sections"] == [] and side["grid"]["anchor"] == 0.5


def test_put_sections_validation(env, click_track_file):  # noqa: F811
    c, svc, tmp = env
    p = _analysed(c, tmp, click_track_file)
    bad = [{"start": 0, "end": 10, "label": "Intro"}, {"start": 8, "end": 20, "label": "Verso"}]
    assert c.put("/analysis/sections", json={"path": str(p), "sections": bad}, headers=H).status_code == 422
    unknown = [{"start": 0, "end": 10, "label": "Coro"}]
    assert c.put("/analysis/sections", json={"path": str(p), "sections": unknown}, headers=H).status_code == 422
    beyond = [{"start": 0, "end": 999, "label": "Intro"}]
    assert c.put("/analysis/sections", json={"path": str(p), "sections": beyond}, headers=H).status_code == 422
    ok = [{"start": 0, "end": 15, "label": "Intro"}, {"start": 15, "end": 40, "label": "Estribillo/Drop"}]
    r = c.put("/analysis/sections", json={"path": str(p), "sections": ok}, headers=H)
    assert r.status_code == 200 and all(s["source"] == "manual" for s in r.json()["sections"])


def test_reanalysis_keeps_manual_sections_and_reset(env, click_track_file):  # noqa: F811
    c, svc, tmp = env
    p = _analysed(c, tmp, click_track_file)
    mine = [{"start": 0, "end": 40, "label": "Verso"}]
    c.put("/analysis/sections", json={"path": str(p), "sections": mine}, headers=H)
    c.post("/jobs", json={"type": "analysis", "paths": [str(p)], "force": True}, headers=H)
    time.sleep(0.2)
    wait(c, lambda js: len(final(js, "analysis")) >= 2)
    assert [s.label for s in svc.analysis.get_sections(p)] == ["Verso"]
    r = c.put("/analysis/sections", json={"path": str(p), "reset": True}, headers=H).json()
    assert r["sections"] == svc.analysis.read_sidecar(p)["sections_auto"]
