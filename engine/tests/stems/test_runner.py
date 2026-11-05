import asyncio
import os

import mutagen
import numpy as np
import pytest
import soundfile as sf

from djengine.app_paths import AppPaths
from djengine.errors import JobCancelled
from djengine.library import TrackRecord
from djengine.server import build_services
from djengine.stems import separate as sep_mod
from djengine.stems.runner import make_stems_runner
from djengine.tags import TrackMeta, write_tags

SR = 44100


@pytest.fixture
def svc(tmp_path):
    s = build_services(AppPaths.from_root(tmp_path / "data"), fake=True)
    s.settings.music_dir = str(tmp_path / "music")
    return s


@pytest.fixture
def song(tmp_path, svc):
    t = np.arange(SR * 4) / SR
    y = np.stack([0.3 * np.sin(2 * np.pi * 55 * t), 0.3 * np.sin(2 * np.pi * 880 * t)]).astype(np.float32)
    p = tmp_path / "song.wav"
    sf.write(p, y.T, SR)
    write_tags(p, TrackMeta("LA GRACIOSA", "Quevedo"), None)
    svc.library.add_track(TrackRecord(None, "v1", "LA GRACIOSA", "Quevedo", "", 4, None, str(p), "wav", None, None, ""))
    return p


def run(svc, ctx, path, wanted, karaoke=False):
    return asyncio.run(make_stems_runner(svc, path, wanted, karaoke)(ctx))


def folder(svc):
    return svc.paths.root.parent / "music" / "Stems" / "Quevedo - LA GRACIOSA"


def test_writes_only_wanted_stems_as_wav16(svc, ctx, song):
    r = run(svc, ctx, song, ["vocals", "drums", "bass"])
    f = folder(svc)
    assert sorted(p.name for p in f.iterdir()) == ["bass.wav", "drums.wav", "vocals.wav"]
    info = sf.info(f / "vocals.wav")
    assert (info.samplerate, info.subtype, info.channels) == (44100, "PCM_16", 2)
    assert r["folder"] == str(f) and set(r["stems"]) == {"vocals", "drums", "bass"}
    assert "separating" in [s[0] for s in ctx.reports]


@pytest.mark.parametrize("fmt,check", [
    ("wav24", lambda p: sf.info(p).subtype == "PCM_24"),
    ("flac", lambda p: type(mutagen.File(p)).__name__ == "FLAC"),
    ("mp3", lambda p: type(mutagen.File(p)).__name__ == "MP3" and mutagen.File(p).info.bitrate >= 300000),
])
def test_formats(svc, ctx, song, fmt, check):
    svc.settings.stems_format = fmt
    r = run(svc, ctx, song, ["vocals"])
    assert check(r["stems"]["vocals"])


def test_cache_then_extend(svc, ctx, song, monkeypatch):
    run(svc, ctx, song, ["vocals"])
    calls = []
    real = sep_mod.FakeSeparator.separate
    monkeypatch.setattr(sep_mod.FakeSeparator, "separate", lambda self, *a, **k: calls.append(1) or real(self, *a, **k))
    run(svc, ctx, song, ["vocals"])
    assert calls == []
    run(svc, ctx, song, ["drums", "guitar"])
    assert calls == [1]
    assert sorted(p.name for p in folder(svc).iterdir()) == ["drums.wav", "guitar.wav", "vocals.wav"]


def test_cancel_leaves_nothing(svc, ctx, song, monkeypatch):
    real = sep_mod.FakeSeparator.separate

    def cancel_mid(self, audio, sr, progress, cancelled):
        ctx.cancelled = True
        return real(self, audio, sr, progress, cancelled)

    monkeypatch.setattr(sep_mod.FakeSeparator, "separate", cancel_mid)
    with pytest.raises(JobCancelled):
        run(svc, ctx, song, ["vocals"])
    assert not folder(svc).exists() or list(folder(svc).iterdir()) == []
    assert svc.stems.get(song) == {}


def test_source_edit_recomputes(svc, ctx, song, monkeypatch):
    run(svc, ctx, song, ["vocals"])
    st = song.stat()
    os.utime(song, (st.st_atime, st.st_mtime + 10))
    calls = []
    real = sep_mod.FakeSeparator.separate
    monkeypatch.setattr(sep_mod.FakeSeparator, "separate", lambda self, *a, **k: calls.append(1) or real(self, *a, **k))
    run(svc, ctx, song, ["vocals"])
    assert calls == [1]


def test_untagged_file_uses_its_name(svc, ctx, tmp_path):
    p = tmp_path / "mi mezcla.wav"
    sf.write(p, np.zeros((SR, 2), dtype=np.float32), SR)
    r = run(svc, ctx, p, ["bass"])
    assert r["folder"].endswith("mi mezcla")
