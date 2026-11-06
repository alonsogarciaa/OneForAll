import hashlib
import struct
import subprocess

import numpy as np
import pytest
import soundfile as sf

from djengine.analysis.store import AnalysisRecord, file_stamp, now_iso
from djengine.app_paths import AppPaths
from djengine.errors import UserError
from djengine.export import serato
from djengine.export.model import Cue, ExportTrack
from djengine.server import build_services
from djengine.tags import TrackMeta, read_tags, write_tags
from djengine.tools import find_tool

CUES = [Cue(0.5, "Intro", (142, 142, 147), 0), Cue(15.0, "Canción ñ", (255, 69, 58), 1), Cue(30.0, "Outro", (99, 99, 102), 2)]


def make(tmp_path, ext):
    wav = tmp_path / "src.wav"
    t = np.arange(44100 * 2) / 44100
    sf.write(wav, np.stack([0.2 * np.sin(2 * np.pi * 440 * t)] * 2).T, 44100)
    out = tmp_path / f"song.{ext}"
    codec = {"mp3": ["-c:a", "libmp3lame"], "flac": ["-c:a", "flac"], "m4a": ["-c:a", "aac"], "wav": []}[ext]
    subprocess.run([find_tool("ffmpeg"), "-v", "error", "-y", "-i", str(wav), *codec, str(out)], check=True)
    write_tags(out, TrackMeta("Mi título", "Artista"), None)
    return out


def track(path):
    return ExportTrack(1, str(path), "Mi título", "Artista", "", 2.0, path.stat().st_size, 128.0, "Am", 0.5, CUES,
                       "MP3 File")


def mp3_audio_hash(path):
    data = path.read_bytes()
    if data[:3] == b"ID3":
        size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        data = data[10 + size:]
    return hashlib.sha1(data).hexdigest()


def test_beatgrid_bytes():
    b = serato.encode_beatgrid(0.5, 128.0)
    assert b == b"\x01\x00" + struct.pack(">I", 1) + struct.pack(">f", 0.5) + struct.pack(">f", 128.0) + b"\x00"
    assert serato.decode_beatgrid(b) == (0.5, 128.0)


def test_autotags_bytes():
    assert serato.encode_autotags(128.0) == b"\x01\x01128.00\x000.000\x000.000\x00"


def test_markers2_round_trip():
    content = serato.encode_markers2(CUES)
    assert content[:2] == b"\x01\x01" and len(content) >= 470
    got = serato.decode_markers2(content)
    assert [(c.hot, round(c.start * 1000), c.color, c.name) for c in got] == [
        (0, 500, (142, 142, 147), "Intro"), (1, 15000, (255, 69, 58), "Canción ñ"), (2, 30000, (99, 99, 102), "Outro")]


def test_only_hot_cues_go_to_markers2():
    many = [Cue(float(i), f"S{i}", (1, 2, 3), i if i < 8 else None) for i in range(10)]
    assert len(serato.decode_markers2(serato.encode_markers2(many))) == 8


def test_write_mp3_round_trip_keeps_audio_and_other_tags(tmp_path):
    p = make(tmp_path, "mp3")
    before = mp3_audio_hash(p)
    serato.write_serato(p, track(p))
    got = serato.read_serato(p)
    assert got["bpm"] == 128.0 and got["grid"] == (0.5, 128.0) and [c.name for c in got["cues"]] == ["Intro", "Canción ñ", "Outro"]
    assert read_tags(p).title == "Mi título" and mp3_audio_hash(p) == before


@pytest.mark.parametrize("ext", ["flac", "m4a"])
def test_write_flac_m4a_round_trip(tmp_path, ext):
    p = make(tmp_path, ext)
    serato.write_serato(p, track(p))
    got = serato.read_serato(p)
    assert got["grid"] == (0.5, 128.0) and len(got["cues"]) == 3 and read_tags(p).title == "Mi título"


def test_write_twice_replaces(tmp_path):
    from mutagen.id3 import ID3

    p = make(tmp_path, "mp3")
    serato.write_serato(p, track(p))
    serato.write_serato(p, track(p))
    assert len(ID3(p).getall("GEOB")) == 3


def test_wav_unsupported(tmp_path):
    p = make(tmp_path, "wav")
    with pytest.raises(UserError) as e:
        serato.write_serato(p, track(p))
    assert e.value.message == "Formato no compatible con Serato"


def test_restamp_after_write(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "0")
    svc = build_services(AppPaths.from_root(tmp_path / "data"), fake=True)
    p = make(tmp_path, "mp3")
    size, mtime = file_stamp(p)
    svc.analysis.save(AnalysisRecord(path=str(p), size=size, mtime=mtime, bpm=128.0, bpm_confidence=0.9,
                                     bpm_source="auto", tonic="A", mode="minor", camelot="8A", key_confidence=0.8,
                                     lufs=-9.0, peak_db=-1.0, version=2, created_at=now_iso()),
                      {"beats": [], "waveform": {}, "duration": 2.0})
    serato.export_serato(svc, track(p))
    assert svc.analysis.get(p) is not None


def test_locked_file_is_reported_as_busy(tmp_path):
    import os
    import stat

    p = make(tmp_path, "mp3")
    os.chmod(p, stat.S_IREAD)
    try:
        with pytest.raises(UserError) as e:
            serato.write_serato(p, track(p))
        assert e.value.message == "Archivo en uso"
    finally:
        os.chmod(p, stat.S_IWRITE | stat.S_IREAD)


def test_flac_m4a_autotags_keys_match_serato():
    assert serato.FLAC_KEYS["autotags"] == "SERATO_AUTOGAIN"
    assert serato.MP4_KEYS["autotags"] == "----:com.serato.dj:autgain"
