import subprocess

import numpy as np
import pytest
import soundfile as sf

from djengine.analysis.store import AnalysisRecord, file_stamp, now_iso
from djengine.app_paths import AppPaths
from djengine.export.model import Cue, collect, cues_for, english_key, mp3_decoder_offset
from djengine.library import TrackRecord
from djengine.prep.grid import Grid
from djengine.prep.sections import COLORS, Section
from djengine.server import build_services
from djengine.tools import find_tool


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "0")
    return build_services(AppPaths.from_root(tmp_path / "data"), fake=True)


def add(svc, path, analysed=True, sections=()):
    tid = svc.library.add_track(TrackRecord(None, None, path.stem, "Art", "Alb", 10, None, str(path), path.suffix[1:], None, None, ""))
    if analysed:
        size, mtime = file_stamp(path)
        svc.analysis.save(AnalysisRecord(path=str(path), size=size, mtime=mtime, bpm=128.0, bpm_confidence=0.9,
                                         bpm_source="auto", tonic="A", mode="minor", camelot="8A", key_confidence=0.8,
                                         lufs=-9.0, peak_db=-1.0, version=2, created_at=now_iso()),
                          {"beats": [], "waveform": {}, "duration": 10.0, "grid": Grid(0.5, 128.0).to_dict(),
                           "sections": [s.to_dict() for s in sections]})
    return tid


def test_english_key():
    assert english_key("A", "minor") == "Am" and english_key("F#", "major") == "F#" and english_key(None, None) == ""


def test_cues_for():
    secs = [Section(i * 10.0, i * 10.0 + 10, "Verso" if i % 2 else "Estribillo/Drop") for i in range(10)]
    cues = cues_for(secs)
    assert len(cues) == 10 and [c.hot for c in cues] == [0, 1, 2, 3, 4, 5, 6, 7, None, None]
    assert cues[0] == Cue(0.0, "Estribillo/Drop", COLORS["Estribillo/Drop"], 0)


def test_collect_skips(svc, tmp_path):
    a = tmp_path / "a.wav"
    sf.write(a, np.zeros((4410, 2), dtype=np.float32), 44100)
    b = tmp_path / "b.wav"
    sf.write(b, np.zeros((4410, 2), dtype=np.float32), 44100)
    gone = tmp_path / "gone.wav"
    gone.write_bytes(b"x")
    ia = add(svc, a, sections=[Section(0, 10, "Intro")])
    ib = add(svc, b, analysed=False)
    ig = add(svc, gone, analysed=False)
    gone.unlink()
    tracks, skipped = collect(svc, None)
    assert [t.id for t in tracks] == [ia]
    t = tracks[0]
    assert (t.bpm, t.key, t.anchor, t.kind, t.artist) == (128.0, "Am", 0.5, "WAV File", "Art")
    assert t.cues[0].name == "Intro" and t.size == a.stat().st_size
    reasons = {s["title"]: s["reason"] for s in skipped}
    assert reasons == {"b": "Sin analizar", "gone": "Archivo no encontrado"}
    assert [x.id for x in collect(svc, [ib, ia])[0]] == [ia]
    assert ig


def test_mp3_offset(tmp_path):
    wav = tmp_path / "s.wav"
    sf.write(wav, np.zeros((44100, 2), dtype=np.float32), 44100)
    mp3 = tmp_path / "s.mp3"
    subprocess.run([find_tool("ffmpeg"), "-v", "error", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)], check=True)
    off = mp3_decoder_offset(mp3)
    assert 0.02 < off < 0.06  # LAME: encoder delay + 529 decoder samples at 44.1 kHz
    assert mp3_decoder_offset(wav) == 0.0
    raw = tmp_path / "raw.mp3"
    subprocess.run([find_tool("ffmpeg"), "-v", "error", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-write_xing", "0", str(raw)], check=True)
    assert mp3_decoder_offset(raw) == 0.0


def test_library_playlists(svc, tmp_path):
    pl = svc.library.add_playlist("PL1", "Perreo", str(tmp_path))
    svc.library.add_playlist_track(pl, 7, 1)
    svc.library.add_playlist_track(pl, 5, 0)
    assert svc.library.list_playlists() == [(pl, "Perreo")]
    assert svc.library.playlist_track_ids(pl) == [5, 7]
