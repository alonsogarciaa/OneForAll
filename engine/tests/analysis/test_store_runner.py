import asyncio
import json
import os

import numpy as np
import pytest

from djengine.analysis import runner as runner_mod
from djengine.analysis.runner import make_analysis_runner
from djengine.app_paths import AppPaths
from djengine.errors import JobCancelled
from djengine.library import TrackRecord
from djengine.server import build_services
from djengine.tags import TrackMeta, read_tags, write_tags

SR = 22050


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_mod, "DEFAULT_TEMPO_METHOD", "librosa")
    monkeypatch.setattr(runner_mod, "DEFAULT_KEY_METHOD", "edma")
    return build_services(AppPaths.from_root(tmp_path / "data"), fake=True)


@pytest.fixture
def song(tmp_path, click_track, chord_progression, write_wav, svc):
    y = 0.6 * chord_progression("A", "minor") + 0.5 * click_track(128)
    p = write_wav(y.astype(np.float32), SR, "song.wav")
    write_tags(p, TrackMeta("La Graciosa", "Quevedo"), None)
    svc.library.add_track(TrackRecord(None, "v1", "La Graciosa", "Quevedo", "", 30, None, str(p), "wav", None, None, ""))
    return p


def run(svc, ctx, path, **kw):
    return asyncio.run(make_analysis_runner(svc, path, **kw)(ctx))


def test_full_analysis_saves_row_sidecar_tags_and_library(svc, ctx, song):
    r = run(svc, ctx, song)
    rec = svc.analysis.get(song)
    assert abs(rec.bpm - 128) <= 1 and rec.camelot == "8A" and rec.bpm_source == "auto"
    side = svc.analysis.get_sidecar(song)
    # librosa trims weak leading beats (chord onsets dominate the clicks here); spacing must match the tempo
    assert len(side["beats"]) > 25 and len(side["waveform"]["peaks"]) == 2000
    assert abs(float(np.median(np.diff(side["beats"]))) - 60 / 128) < 0.02
    t = read_tags(song)
    assert t.bpm == 128.0 and t.key == "8A" and t.title == "La Graciosa"
    lib = svc.library.list_tracks()[0]
    assert lib.camelot == "8A" and abs(lib.bpm - 128) <= 1
    assert r["display_key"] == "8A · Lam"
    assert [s[0] for s in ctx.reports][:2] == ["decoding", "tempo"]


def test_musical_notation(svc, ctx, song):
    svc.settings.key_notation = "musical"
    run(svc, ctx, song)
    assert read_tags(song).key == "Am"


def test_cache_hit_and_invalidation(svc, ctx, song, monkeypatch):
    run(svc, ctx, song)
    calls = []
    real = runner_mod.decode
    monkeypatch.setattr(runner_mod, "decode", lambda *a, **k: calls.append(1) or real(*a, **k))
    run(svc, ctx, song)
    assert calls == []
    st = song.stat()
    os.utime(song, (st.st_atime, st.st_mtime + 10))
    run(svc, ctx, song)
    assert calls


def test_manual_bpm_survives_reanalysis(svc, ctx, song):
    run(svc, ctx, song)
    svc.analysis.set_manual_bpm(song, 127.0)
    run(svc, ctx, song, force=True)
    rec = svc.analysis.get(song)
    assert (rec.bpm, rec.bpm_source) == (127.0, "manual")
    run(svc, ctx, song, reset_bpm=True)
    rec = svc.analysis.get(song)
    assert rec.bpm_source == "auto" and abs(rec.bpm - 128) <= 1


def test_cancel_leaves_nothing(svc, ctx, song, monkeypatch):
    real = runner_mod.estimate_key

    def cancel_then(*a, **k):
        ctx.cancelled = True
        return real(*a, **k)

    monkeypatch.setattr(runner_mod, "estimate_key", cancel_then)
    with pytest.raises(JobCancelled):
        run(svc, ctx, song)
    assert svc.analysis.get(song) is None and svc.analysis.get_sidecar(song) is None


def test_short_silent_file_has_no_nan(svc, ctx, write_wav):
    p = write_wav(np.zeros(3 * SR, dtype=np.float32), SR, "silent.wav")
    run(svc, ctx, p)
    rec = svc.analysis.get(p)
    json.dumps(rec.__dict__, allow_nan=False)
    json.dumps(svc.analysis.get_sidecar(p), allow_nan=False)


def test_settings_validation():
    from pydantic import ValidationError

    from djengine.settings import Settings

    s = Settings()
    assert (s.analyze_on_download, s.key_notation, s.bpm_min, s.bpm_max) == (True, "camelot", 70, 180)
    with pytest.raises(ValidationError):
        Settings(bpm_min=180, bpm_max=70)
