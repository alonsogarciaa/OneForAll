import asyncio
import os
import subprocess
from pathlib import Path

import pytest
from mutagen.id3 import GEOB, ID3

from djengine.analysis.store import AnalysisRecord, file_stamp, now_iso
from djengine.app_paths import AppPaths
from djengine.enhance import runner as er
from djengine.enhance.runner import enhanced_name, make_enhance_runner, submit_enhance, target_codec
from djengine.library import TrackRecord
from djengine.server import build_services
from djengine.tags import TrackMeta, read_cover, read_tags, write_tags
from djengine.tools import find_tool

FINAL = ("done", "failed", "cancelled")
COVER = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "0")
    monkeypatch.setenv("ONEFORALL_FAKE_ENHANCE", "1")
    s = build_services(AppPaths.from_root(tmp_path / "data"), fake=True)
    s.settings.music_dir = str(tmp_path / "music")
    return s


def _make(path: Path, extra: list[str] | None = None, seconds: int = 4) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([find_tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", f"sine=f=440:d={seconds}", "-ac", "2",
                    "-ar", "44100", *(extra or []), "-y", str(path)], check=True)
    return path


@pytest.fixture
def song(tmp_path, svc):
    p = _make(tmp_path / "music" / "Song.mp3", ["-c:a", "libmp3lame", "-b:a", "128k"])
    write_tags(p, TrackMeta("Song", "Artist", "Album"), COVER)
    tags = ID3(p)
    tags.add(GEOB(encoding=0, mime="application/octet-stream", desc="Serato Markers2", data=b"serato"))
    tags.save(p)
    svc.library.add_track(TrackRecord(None, "vid1", "Song", "Artist", "Album", 4, None, str(p), "mp3", 128, None, ""))
    size, mtime = file_stamp(p)
    svc.analysis.save(AnalysisRecord(path=str(p), size=size, mtime=mtime, bpm=120.0, bpm_confidence=0.9,
                                     bpm_source="auto", tonic="A", mode="minor", camelot="8A", key_confidence=0.8,
                                     lufs=-30.0, peak_db=-20.0, version=2, created_at=now_iso()),
                      {"beats": [], "waveform": {}, "duration": 4.0, "grid": {"anchor": 0.5, "bpm": 120.0}})
    return p


async def _wait(svc, job):
    while svc.jobs.get(job.id).status not in FINAL:
        await asyncio.sleep(0.02)
    return svc.jobs.get(job.id)


async def _run(svc, path, mode, fmt):
    return await _wait(svc, svc.jobs.submit("enhance", "t", make_enhance_runner(svc, path, mode, fmt)))


def test_enhanced_name():
    assert enhanced_name("Song") == "Song (Mejorado)"


@pytest.mark.parametrize("name,fmt,ext,args", [
    ("a.mp3", "same", "mp3", ["-c:a", "libmp3lame", "-b:a", "320k"]),
    ("a.m4a", "same", "m4a", ["-c:a", "aac", "-b:a", "320k"]),
    ("a.opus", "same", "opus", ["-c:a", "libopus", "-b:a", "256k"]),
    ("a.ogg", "same", "ogg", ["-c:a", "libvorbis", "-q:a", "10"]),
    ("a.mp3", "flac", "flac", ["-c:a", "flac", "-sample_fmt", "s32"]),
])
def test_target_codec_lossy_and_flac(tmp_path, name, fmt, ext, args):
    assert target_codec(Path(name), fmt, ("x", None)) == (ext, args)


@pytest.mark.parametrize("name,probe,args", [
    ("a.flac", ("flac", 24), ["-c:a", "flac", "-sample_fmt", "s32"]),
    ("a.flac", ("flac", 16), ["-c:a", "flac", "-sample_fmt", "s16"]),
    ("a.wav", ("pcm_s24le", 24), ["-c:a", "pcm_s24le"]),
    ("a.wav", ("pcm_s16le", 16), ["-c:a", "pcm_s16le"]),
    ("a.aiff", ("pcm_s24be", 24), ["-c:a", "pcm_s24be"]),
    ("a.m4a", ("alac", 16), ["-c:a", "alac"]),
])
def test_target_codec_lossless_keeps_depth(name, probe, args):
    assert target_codec(Path(name), "same", probe)[1] == args


async def test_copy_same_format(svc, song):
    job = await _run(svc, song, "copy", "same")
    assert job.status == "done", job.error
    out = Path(job.result["path"])
    assert out == song.with_name("Song (Mejorado).mp3") and out.is_file() and song.is_file()
    meta = read_tags(out)
    assert (meta.title, meta.artist, meta.album) == ("Song", "Artist", "Album")
    assert read_cover(out) == COVER
    assert ID3(out).getall("GEOB")[0].data == b"serato"
    t = svc.library.track_by_path(str(out))
    assert t.enhanced and t.origin_video_id == "vid1"
    rec = svc.analysis.get(out)
    assert rec.bpm == 120.0 and rec.lufs != -30.0
    assert svc.analysis.read_sidecar(out)["grid"]["anchor"] == 0.5
    assert any(h.action == "enhance" for h in svc.library.list_history())


async def test_replace_same_format_keeps_path_and_backup(svc, song):
    job = await _run(svc, song, "replace", "same")
    assert job.status == "done", job.error
    assert Path(job.result["path"]) == song and song.is_file()
    backup = Path(svc.settings.music_dir) / "Originales" / "Song.mp3"
    assert Path(job.result["backup"]) == backup and backup.is_file()
    assert svc.library.track_by_path(str(song)).enhanced
    assert svc.analysis.get(song).bpm == 120.0  # stamps refreshed: the analysis still counts
    assert ID3(song).getall("GEOB")[0].data == b"serato"


async def test_replace_to_flac_moves_library_and_sidecar(svc, song):
    job = await _run(svc, song, "replace", "flac")
    assert job.status == "done", job.error
    flac = song.with_suffix(".flac")
    assert Path(job.result["path"]) == flac and flac.is_file() and not song.exists()
    assert job.result["moved_from"] == str(song)
    assert (Path(svc.settings.music_dir) / "Originales" / "Song.mp3").is_file()
    t = svc.library.track_by_path(str(flac))
    assert t and t.format == "flac" and t.enhanced and svc.library.track_by_path(str(song)) is None
    assert svc.analysis.get(flac).bpm == 120.0 and svc.analysis.get(song) is None
    assert read_tags(flac).title == "Song" and read_cover(flac) == COVER


async def test_commit_failure_puts_the_original_back(svc, song, monkeypatch):
    from djengine.errors import user_error

    def boom(tmp, final):
        raise user_error("disk")

    monkeypatch.setattr(er, "_commit", boom)
    job = await _run(svc, song, "replace", "same")
    assert job.status == "failed" and job.error["code"] == "disk"
    assert song.is_file() and not (Path(svc.settings.music_dir) / "Originales" / "Song.mp3").exists()


async def test_file_in_use_is_not_touched(svc, song, monkeypatch):
    real = os.replace

    def busy(a, b):
        if Path(a) == song:
            raise PermissionError(13, "in use")
        return real(a, b)

    monkeypatch.setattr(er.os, "replace", busy)
    before = song.read_bytes()
    job = await _run(svc, song, "replace", "same")
    assert job.status == "failed" and job.error["code"] == "file_busy"
    assert job.error["message"] == "Archivo en uso: ciérralo en tu programa DJ"
    assert song.read_bytes() == before


async def test_cancel_leaves_nothing(svc, tmp_path, monkeypatch):
    long = _make(tmp_path / "music" / "Long.wav", seconds=40)
    before = long.read_bytes()
    monkeypatch.setattr(er, "_chunk_delay", lambda: 0.2, raising=False)
    job = svc.jobs.submit("enhance", "t", make_enhance_runner(svc, long, "replace", "same"))
    for _ in range(1000):
        j = svc.jobs.get(job.id)
        if j.stage == "restoring" or j.status in FINAL:
            break
        await asyncio.sleep(0.01)
    assert j.stage == "restoring", (j.status, j.error)
    await svc.jobs.cancel(job.id)
    j = await _wait(svc, job)
    assert j.status == "cancelled"
    assert long.read_bytes() == before
    assert not list((tmp_path / "music").rglob("*.part")) and not (tmp_path / "music" / "Originales").exists()


async def test_same_path_twice_is_one_job(svc, song):
    a = submit_enhance(svc, song, "copy", "same")
    b = submit_enhance(svc, song, "replace", "flac")
    assert a.id == b.id
    await _wait(svc, a)


async def test_then_stems_runs_on_the_result(svc, song):
    from djengine.pipelines import ThenStems

    job = await _wait(svc, submit_enhance(svc, song, "copy", "same", then_stems=ThenStems(stems=["vocals"])))
    stems = [j for j in svc.jobs.list() if j.type == "stems"]
    assert stems and stems[0].payload["paths"] == [job.result["path"]]


def test_enhance_api(svc, song):
    from fastapi.testclient import TestClient

    from djengine.server import create_app

    H = {"X-Token": "t"}
    with TestClient(create_app(svc, token="t")) as c:
        r = c.post("/jobs", json={"type": "enhance", "path": str(song), "mode": "copy", "format": "same"}, headers=H)
        assert r.status_code == 200 and r.json()["job"]["type"] == "enhance"
        r = c.post("/jobs", json={"type": "enhance", "path": str(song), "mode": "move", "format": "same"}, headers=H)
        assert r.status_code == 422
        r = c.get("/enhance/estimate", params={"path": str(song)}, headers=H)
        assert r.status_code == 200 and r.json() == {"seconds": None}
        svc.settings.enhance_rtf = 3.5
        assert abs(c.get("/enhance/estimate", params={"path": str(song)}, headers=H).json()["seconds"] - 14.0) < 0.5


@pytest.mark.parametrize("ext,codec", [("mp3", ["-c:a", "libmp3lame"]), ("m4a", ["-c:a", "aac"]),
                                       ("opus", ["-c:a", "libopus", "-ar", "48000"]), ("ogg", ["-c:a", "libvorbis"])])
async def test_every_lossy_format_really_encodes(svc, tmp_path, ext, codec):
    src = _make(tmp_path / "music" / f"S.{ext}", codec)
    job = await _run(svc, src, "copy", "same")
    assert job.status == "done", job.error
    assert Path(job.result["path"]).suffix == f".{ext}"


async def test_replace_across_drives_copies_the_backup(svc, song, monkeypatch):
    real = os.replace
    backup_dir = Path(svc.settings.music_dir) / "Originales"

    def cross(a, b):
        if Path(a) == song and Path(b).parent == backup_dir:
            e = OSError(18, "cross-device")
            e.winerror = 17
            raise e
        return real(a, b)

    monkeypatch.setattr(er.os, "replace", cross)
    job = await _run(svc, song, "replace", "same")
    assert job.status == "done", job.error
    assert (backup_dir / "Song.mp3").is_file() and song.is_file()


async def test_failed_enhance_still_runs_the_requested_analysis_and_stems(svc, song, monkeypatch):
    from djengine.errors import UserError
    from djengine.pipelines import ThenStems

    def boom(*a, **k):
        raise UserError("model_missing", "No se pudo descargar el modelo de mejora")

    monkeypatch.setattr(er, "_restore", boom)
    job = await _wait(svc, submit_enhance(svc, song, "replace", "same", then_stems=ThenStems(stems=["vocals"]),
                                          analyze_after=True))
    assert job.status == "failed"
    kinds = {j.type: j.payload for j in svc.jobs.list() if j.type in ("stems", "analysis")}
    assert kinds["stems"]["paths"] == [str(song)] and kinds["analysis"]["paths"] == [str(song)]
