"""Deferred minor findings, group A (API and stems)."""
import os
import threading
import zipfile

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from djengine.app_paths import AppPaths
from djengine.errors import UserError
from djengine.library import TrackRecord
from djengine.server import build_services, create_app
from djengine.stems import separate as sep_mod
from djengine.stems.store import StemsStore
from tests.stems.test_runner import folder, run, song, svc  # noqa: F401

H = {"X-Token": "t"}


@pytest.fixture
def api(svc):  # noqa: F811
    with TestClient(create_app(svc, token="t")) as c:
        yield c


def test_harmonic_rejects_unknown_camelot(api):
    assert api.get("/harmonic", params={"bpm": 128, "camelot": "abc"}, headers=H).status_code == 422
    assert api.get("/harmonic", params={"bpm": 128, "camelot": "13A"}, headers=H).status_code == 422


def test_manual_bpm_refused_on_stale_analysis(api, svc, ctx, song):  # noqa: F811
    import asyncio

    from djengine.analysis.runner import make_analysis_runner

    asyncio.run(make_analysis_runner(svc, song)(ctx))
    st = song.stat()
    os.utime(song, (st.st_atime, st.st_mtime + 30))  # edited elsewhere since the analysis
    r = api.put("/analysis/bpm", json={"path": str(song), "bpm": 120}, headers=H)
    assert r.status_code == 409


@pytest.mark.skipif(os.name != "nt", reason="case-insensitive paths are a Windows thing")
def test_store_keys_ignore_path_case(tmp_path):
    st = StemsStore(tmp_path / "db")
    src = tmp_path / "Song.wav"
    src.write_bytes(b"x")
    stem = tmp_path / "vocals.wav"
    stem.write_bytes(b"y")
    st.add(src, "vocals", stem, "m")
    assert st.get(str(src).upper()) == {"vocals": stem}
    assert st.is_stem_file(str(stem).upper())


def test_concurrent_zips_both_succeed(api, svc, ctx, song):  # noqa: F811
    run(svc, ctx, song, ["vocals", "drums"])
    results = []

    def go():
        results.append(api.post("/stems/zip", json={"path": str(song)}, headers=H).status_code)

    threads = [threading.Thread(target=go) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results == [200, 200, 200]
    z = next(folder(svc).glob("*.zip"))
    assert sorted(zipfile.ZipFile(z).namelist()) == ["drums.wav", "vocals.wav"]


def test_format_change_removes_old_format_files(svc, ctx, song):  # noqa: F811
    run(svc, ctx, song, ["vocals"])
    svc.settings.stems_format = "flac"
    st = song.stat()
    os.utime(song, (st.st_atime, st.st_mtime + 30))  # stale: will recompute
    run(svc, ctx, song, ["vocals"])
    assert sorted(p.name for p in folder(svc).iterdir()) == ["vocals.flac"]


def test_karaoke_with_cached_vocals_skips_demucs(svc, ctx, song, monkeypatch):  # noqa: F811
    run(svc, ctx, song, ["vocals"])
    calls = []
    real = sep_mod.FakeSeparator.separate
    monkeypatch.setattr(sep_mod.FakeSeparator, "separate", lambda self, *a, **k: calls.append(1) or real(self, *a, **k))
    r = run(svc, ctx, song, ["vocals"], karaoke=True)
    assert calls == [] and {"lead_vocals", "backing_vocals"} <= set(r["stems"])


def test_karaoke_unexpected_outputs_raise_user_error(tmp_path, monkeypatch):
    from djengine.stems import karaoke

    class FakeSep:
        def __init__(self, **k):
            pass

        def load_model(self, **k):
            pass

        def separate(self, src):
            return ["weird_name.wav"]

    import audio_separator.separator as asep

    monkeypatch.setattr(asep, "Separator", FakeSep)
    k = karaoke.UvrKaraoke(tmp_path / "uvr")
    with pytest.raises(UserError):
        k.split(np.zeros((2, 4410), dtype=np.float32), 44100, tmp_path / "w")


def test_tools_dir_is_on_path_after_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEFORALL_TOOLS", str(tmp_path / "tools"))
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "ffmpeg.exe").write_bytes(b"")
    build_services(AppPaths.from_root(tmp_path / "data"), fake=True)
    assert str(tmp_path / "tools") in os.environ["PATH"].split(os.pathsep)


def test_uvr_karaoke_is_shared(svc):  # noqa: F811
    from djengine.stems.karaoke import UvrKaraoke, get_karaoke

    a = get_karaoke(svc, object())
    b = get_karaoke(svc, object())
    assert isinstance(a, UvrKaraoke) and a is b
