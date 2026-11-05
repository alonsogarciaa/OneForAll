"""Deferred minor findings, group C (playlists)."""
from pathlib import Path

from fastapi.testclient import TestClient

from djengine.convert import ConvertOptions
from djengine.pipelines import start_playlist
from djengine.server import create_app
from tests.test_api import H, wait_job
from tests.test_pipelines import music_dir, svc, wait_done  # noqa: F401


async def test_playlist_dedupes_repeated_tracks(svc, monkeypatch):  # noqa: F811
    real = svc.search.get_playlist

    def doubled(pid):
        info = real(pid)
        info.tracks = info.tracks + [info.tracks[0]]
        return info

    monkeypatch.setattr(svc.search, "get_playlist", doubled)
    job = await start_playlist(svc, "PLfake", ConvertOptions(format="mp3"))
    await wait_done(svc.jobs, job.id)
    kids = [j for j in svc.jobs.list() if j.parent_id == job.id]
    assert len(kids) == len(real("PLfake").tracks)


async def test_playlist_children_carry_destination(svc, music_dir):  # noqa: F811
    job = await start_playlist(svc, "PLfake", ConvertOptions(format="mp3"))
    await wait_done(svc.jobs, job.id)
    kid = next(j for j in svc.jobs.list() if j.parent_id == job.id)
    assert Path(kid.payload["dest_dir"]) == music_dir / "Fake Playlist"
    assert kid.payload["playlist_id"] is not None
    failed = svc.jobs.get(job.id).result["failed"][0]
    assert Path(failed["dest_dir"]) == music_dir / "Fake Playlist" and failed["playlist_id"] is not None


def test_retry_into_playlist_folder(svc, music_dir):  # noqa: F811
    with TestClient(create_app(svc, token="t")) as c:
        target = svc.search.get_playlist("PLfake").tracks[0].model_dump()
        dest = music_dir / "Fake Playlist"
        body = {"type": "download", "request": {"target": target, "options": {"format": "mp3"}, "force": True},
                "dest_dir": str(dest)}
        j = c.post("/jobs", json=body, headers=H).json()["job"]
        assert wait_job(c, j["id"])["status"] == "done"
        assert len(list(dest.glob("*.mp3"))) == 1


def test_retry_dest_outside_music_dir_refused(svc, tmp_path):  # noqa: F811
    with TestClient(create_app(svc, token="t")) as c:
        target = svc.search.get_playlist("PLfake").tracks[0].model_dump()
        body = {"type": "download", "request": {"target": target, "options": {"format": "mp3"}, "force": True},
                "dest_dir": str(tmp_path / "elsewhere")}
        assert c.post("/jobs", json=body, headers=H).status_code == 422
