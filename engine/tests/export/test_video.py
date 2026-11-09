import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from djengine.analysis.store import AnalysisRecord, file_stamp, now_iso
from djengine.app_paths import AppPaths
from djengine.export import video as vx
from djengine.export.video import make_video_export_runner, video_args
from djengine.library import TrackRecord
from djengine.server import build_services
from djengine.tags import TrackMeta, write_tags
from djengine.tools import find_tool

FINAL = ("done", "failed", "cancelled")
def _png() -> bytes:
    import io

    from PIL import Image

    b = io.BytesIO()
    Image.new("RGB", (600, 600), (200, 30, 30)).save(b, "PNG")
    return b.getvalue()


COVER = _png()


def _joined(args):
    return " ".join(args)


def test_video_args_for_a_video():
    a = video_args(Path("a.mp3"), Path("v.mp4"), still=False, quality="1080", speed=1.0, out=Path("o.mp4"))
    s = _joined(a)
    for part in ("-c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p", "-c:a aac -b:a 320k",
                 "-movflags +faststart", "-shortest"):
        assert part in s
    assert "tpad=stop_mode=clone" in a[a.index("-vf") + 1]
    assert "setpts" not in s


def test_video_args_follow_the_tempo_of_a_copy():
    a = video_args(Path("a.mp3"), Path("v.mp4"), still=False, quality="1080", speed=124 / 128, out=Path("o.mp4"))
    assert "setpts=PTS*1.032258" in a[a.index("-vf") + 1]


@pytest.mark.parametrize("quality,width", [("1080", "1920"), ("max", "1920"), ("720", "1280")])
def test_video_args_still_image(quality, width):
    a = video_args(Path("a.mp3"), Path("c.jpg"), still=True, quality=quality, speed=1.0, out=Path("o.mp4"))
    s = _joined(a)
    assert "-loop 1 -framerate 2" in s and "-tune stillimage" in s
    assert width in a[a.index("-vf") + 1]


def _probe_duration(p: Path) -> float:
    r = subprocess.run([find_tool("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(p)],
                       capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def _has_video(p: Path) -> bool:
    r = subprocess.run([find_tool("ffprobe"), "-v", "error", "-select_streams", "v", "-show_entries", "stream=codec_name",
                        "-of", "json", str(p)], capture_output=True, text=True, check=True)
    return [s["codec_name"] for s in json.loads(r.stdout)["streams"]] == ["h264"]


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "0")
    s = build_services(AppPaths.from_root(tmp_path / "data"), fake=True)
    s.settings.music_dir = str(tmp_path / "music")
    calls = []
    real = s.video_downloader

    async def counting(ctx, url, quality):
        calls.append(url)
        return await real(ctx, url, quality)

    s.video_downloader = counting
    s.calls = calls
    return s


def _track(svc, tmp_path, name, video_id=None, origin=None, cover: bool | bytes = True, seconds=3, bpm=None, origin_bpm=None):
    p = tmp_path / "music" / f"{name}.mp3"
    p.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([find_tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", f"sine=f=440:d={seconds}", "-ac", "2",
                    "-c:a", "libmp3lame", "-y", str(p)], check=True)
    write_tags(p, TrackMeta(name, "Artist"), (cover if isinstance(cover, bytes) else COVER) if cover else None)
    svc.library.add_track(TrackRecord(None, video_id, name, "Artist", "", seconds, None, str(p), "mp3", None, None, "",
                                      origin_video_id=origin))
    if bpm:
        size, mtime = file_stamp(p)
        side = {"beats": [], "waveform": {}, "duration": seconds, "grid": {"anchor": 0.0, "bpm": bpm}}
        if origin_bpm:
            side["origin_bpm"] = origin_bpm
        svc.analysis.save(AnalysisRecord(path=str(p), size=size, mtime=mtime, bpm=bpm, bpm_confidence=1, bpm_source="manual",
                                         tonic=None, mode=None, camelot=None, key_confidence=None, lufs=None, peak_db=None,
                                         version=2, created_at=now_iso()), side)
    return svc.library.track_by_path(str(p))


async def _run(svc, ids, quality="1080"):
    job = svc.jobs.submit("video_export", "t", make_video_export_runner(svc, ids, quality, None))
    while svc.jobs.get(job.id).status not in FINAL:
        await asyncio.sleep(0.05)
    return svc.jobs.get(job.id)


async def test_exports_the_original_video_and_caches_it(svc, tmp_path):
    t = _track(svc, tmp_path, "Song", video_id="vid1")
    j = await _run(svc, [t.id])
    assert j.status == "done", j.error
    out = Path(j.result["exported"][0]["file"])
    assert out == tmp_path / "music" / "Videos" / "Artist - Song.mp4"
    assert abs(_probe_duration(out) - 3.0) < 0.15 and _has_video(out)
    assert j.result["fallbacks"] == [] and len(svc.calls) == 1
    j2 = await _run(svc, [t.id])
    assert j2.status == "done" and len(svc.calls) == 1  # cached
    assert Path(j2.result["exported"][0]["file"]).name == "Artist - Song (1).mp4"


async def test_retempo_copy_uses_the_original_video_with_setpts(svc, tmp_path, monkeypatch):
    seen = []
    real = vx.video_args
    monkeypatch.setattr(vx, "video_args", lambda *a, **k: seen.append(k.get("speed", a[4] if len(a) > 4 else None)) or real(*a, **k))
    t = _track(svc, tmp_path, "Song (124 BPM)", origin="vid1", bpm=124.0, origin_bpm=128.0)
    j = await _run(svc, [t.id])
    assert j.status == "done", j.error
    assert svc.calls and "vid1" in svc.calls[0]
    assert abs(seen[0] - 124 / 128) < 1e-9


async def test_no_video_uses_the_cover(svc, tmp_path):
    t = _track(svc, tmp_path, "Own")
    j = await _run(svc, [t.id], "720")
    assert j.status == "done", j.error
    assert j.result["fallbacks"] == [{"title": "Own", "reason": "Sin vídeo original"}]
    out = Path(j.result["exported"][0]["file"])
    assert _has_video(out) and abs(_probe_duration(out) - 3.0) < 0.15 and not svc.calls


async def test_unavailable_video_falls_back_with_the_reason(svc, tmp_path):
    t = _track(svc, tmp_path, "Gone", video_id="private123")
    j = await _run(svc, [t.id])
    assert j.status == "done", j.error
    assert j.result["fallbacks"] == [{"title": "Gone", "reason": "Este vídeo ya no está disponible"}]
    assert len(j.result["exported"]) == 1


async def test_no_cover_draws_a_title_card(svc, tmp_path):
    t = _track(svc, tmp_path, "Bare", cover=False)
    j = await _run(svc, [t.id])
    assert j.status == "done", j.error
    assert _has_video(Path(j.result["exported"][0]["file"]))


async def test_corrupt_cover_uses_the_title_card_and_ends(svc, tmp_path):
    t = _track(svc, tmp_path, "Broken", cover=bytes([0x89]) + b"PNG" + bytes([13, 10, 26, 10]) + b"not really")
    j = await asyncio.wait_for(_run(svc, [t.id]), 60)
    assert j.status == "done", j.error
    assert _has_video(Path(j.result["exported"][0]["file"]))


async def test_ffmpeg_failure_marks_one_track_and_goes_on(svc, tmp_path, monkeypatch):
    a = _track(svc, tmp_path, "A")
    b = _track(svc, tmp_path, "B")
    real = vx.video_args

    def broken(audio, image, still, quality, speed, out, **kw):
        args = real(audio, image, still, quality, speed, out, **kw)
        return ["-bogus_option"] + args if "A" in Path(audio).stem else args

    monkeypatch.setattr(vx, "video_args", broken)
    j = await _run(svc, [a.id, b.id])
    assert j.status == "done", j.error
    assert j.result["failed"] == [{"title": "A", "reason": "No se pudo crear el vídeo"}]
    assert [e["title"] for e in j.result["exported"]] == ["B"]


async def test_cancel_leaves_no_part(svc, tmp_path):
    t = _track(svc, tmp_path, "Long", video_id="vid1", seconds=60)
    job = svc.jobs.submit("video_export", "t", make_video_export_runner(svc, [t.id], "1080", None))
    for _ in range(1500):
        if svc.jobs.get(job.id).stage == "rendering" or svc.jobs.get(job.id).status in FINAL:
            break
        await asyncio.sleep(0.02)
    assert svc.jobs.get(job.id).stage == "rendering", svc.jobs.get(job.id).error
    await svc.jobs.cancel(job.id)
    while svc.jobs.get(job.id).status not in FINAL:
        await asyncio.sleep(0.02)
    assert svc.jobs.get(job.id).status == "cancelled"
    videos = tmp_path / "music" / "Videos"
    assert not [p for p in videos.rglob("*") if p.suffix in (".part", ".mp4") and ".cache" not in p.parts]


def test_video_export_api(svc, tmp_path):
    from fastapi.testclient import TestClient

    from djengine.server import create_app

    t = _track(svc, tmp_path, "Song")
    H = {"X-Token": "t"}
    with TestClient(create_app(svc, token="t")) as c:
        r = c.post("/jobs", json={"type": "video_export", "track_ids": [t.id], "quality": "720"}, headers=H)
        assert r.status_code == 200 and r.json()["job"]["type"] == "video_export"
        assert c.post("/jobs", json={"type": "video_export", "track_ids": []}, headers=H).status_code == 422
        assert c.post("/jobs", json={"type": "video_export", "track_ids": [t.id], "quality": "4k"}, headers=H).status_code == 422


async def test_title_card_with_percent_in_the_title(svc, tmp_path):
    t = _track(svc, tmp_path, "100% Pure Love", cover=False)
    j = await _run(svc, [t.id])
    assert j.status == "done", j.error
    assert j.result["failed"] == [] and len(j.result["exported"]) == 1
