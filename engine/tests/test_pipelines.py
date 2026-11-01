import asyncio
from pathlib import Path

import pytest

from djengine.convert import ConvertOptions
from djengine.library import TrackRecord
from djengine.pipelines import DownloadRequest, make_convert_runner, make_download_runner, start_playlist
from djengine.search import SearchResult
from djengine.server import build_services
from djengine.tags import read_tags

FINAL = {"done", "failed", "cancelled"}


@pytest.fixture
def music_dir(tmp_path):
    return tmp_path / "music"


@pytest.fixture
def svc(tmp_path, music_dir, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "0")
    from djengine.app_paths import AppPaths

    s = build_services(AppPaths.from_root(tmp_path / "data"), fake=True)
    s.settings.music_dir = str(music_dir)
    return s


def song(artist, title, vid="vid1", url=None) -> SearchResult:
    return SearchResult(kind="song", id=vid, title=title, artist=artist, duration_s=5, views=None,
                        thumbnail=None, url=url or f"https://music.youtube.com/watch?v={vid}")


def submit_download(svc, target, fmt="mp3", force=False):
    req = DownloadRequest(target=target, options=ConvertOptions(format=fmt, quality="320" if fmt == "mp3" else None), force=force)
    return svc.jobs.submit("download", target.title, make_download_runner(svc, req, Path(svc.settings.music_dir)))


async def wait_done(mgr, job_id, timeout=30):
    async def loop():
        while mgr.get(job_id).status not in FINAL:
            await asyncio.sleep(0.02)

    await asyncio.wait_for(loop(), timeout)


async def test_download_end_to_end(svc, music_dir):
    job = submit_download(svc, song("Quevedo", "La Graciosa"))
    await wait_done(svc.jobs, job.id)
    assert svc.jobs.get(job.id).status == "done", svc.jobs.get(job.id).error
    f = music_dir / "Quevedo - La Graciosa.mp3"
    assert f.exists() and read_tags(f).title == "La Graciosa" and read_tags(f).artist == "Quevedo"
    assert svc.library.find_duplicate(None, "Quevedo", "La Graciosa") is not None
    h = svc.library.list_history()[0]
    assert (h.status, h.action) == ("done", "download")
    assert list(svc.paths.tmp_dir.iterdir()) == []


async def test_force_duplicate_goes_to_suffix_same_folder(svc, music_dir):
    for force in (False, True):
        job = submit_download(svc, song("Quevedo", "La Graciosa"), force=force)
        await wait_done(svc.jobs, job.id)
    assert (music_dir / "Quevedo - La Graciosa (1).mp3").exists()
    assert [d for d in music_dir.iterdir() if d.is_dir()] == []


async def test_original_format_keeps_source(svc, music_dir):
    job = submit_download(svc, song("A", "B"), fmt="original")
    await wait_done(svc.jobs, job.id)
    assert svc.jobs.get(job.id).status == "done"
    assert len(list(music_dir.glob("A - B.*"))) == 1


async def test_missing_music_dir_is_created(svc, music_dir):
    svc.settings.music_dir = str(music_dir / "deep" / "er")
    job = svc.jobs.submit("download", "B", make_download_runner(
        svc, DownloadRequest(target=song("A", "B"), options=ConvertOptions(format="mp3")), Path(svc.settings.music_dir)))
    await wait_done(svc.jobs, job.id)
    assert (music_dir / "deep" / "er" / "A - B.mp3").exists()


async def test_unwritable_dest_fails_with_disk(svc, monkeypatch):
    import djengine.pipelines as p

    def deny(*a, **k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(p.os, "replace", deny)
    monkeypatch.setattr(p.shutil, "copy2", deny)
    job = submit_download(svc, song("A", "B"))
    await wait_done(svc.jobs, job.id)
    assert svc.jobs.get(job.id).error["code"] == "disk"
    assert svc.library.list_history()[0].status == "failed"


async def test_cancel_mid_download_leaves_nothing(svc, music_dir, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "5")
    job = submit_download(svc, song("A", "B"))
    await asyncio.sleep(0.5)
    assert await svc.jobs.cancel(job.id)
    await wait_done(svc.jobs, job.id)
    assert svc.jobs.get(job.id).status == "cancelled"
    assert not music_dir.exists() or list(music_dir.iterdir()) == []
    assert list(svc.paths.tmp_dir.iterdir()) == []


async def test_playlist_continues_on_failure_and_skips_existing(svc, music_dir):
    info = svc.search.get_playlist("PLfake")
    existing = info.tracks[1]
    svc.library.add_track(TrackRecord(None, existing.id, existing.title, existing.artist, "", 5, None,
                                      "C:/x.mp3", "mp3", 320, None, ""))
    job = await start_playlist(svc, "PLfake", ConvertOptions(format="mp3"))
    await wait_done(svc.jobs, job.id)
    r = svc.jobs.get(job.id).result
    assert r["done"] == 1 and r["skipped"] == 1
    assert r["failed"][0]["code"] == "unavailable" and r["failed"][0]["title"]
    assert (music_dir / "Fake Playlist").is_dir()
    assert len(list((music_dir / "Fake Playlist").glob("*.mp3"))) == 1


async def test_convert_keeps_original(svc, sine_wav, tmp_path):
    src = tmp_path / "mine.wav"
    src.write_bytes(sine_wav.read_bytes())
    job = svc.jobs.submit("convert", src.name, make_convert_runner(svc, src, ConvertOptions(format="flac")))
    await wait_done(svc.jobs, job.id)
    assert svc.jobs.get(job.id).status == "done"
    assert src.exists() and (tmp_path / "mine.flac").exists()
    assert svc.library.list_history()[0].action == "convert"
