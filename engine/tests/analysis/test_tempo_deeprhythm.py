import builtins
import logging

import pytest

from djengine.analysis import tempo

SR = 22050


def test_deeprhythm_click_track(click_track):
    pytest.importorskip("deeprhythm")
    import djengine.analysis.tempo_deeprhythm  # noqa: F401  (registers the method)

    r = tempo.estimate_tempo(click_track(128, seconds=40), SR, method="deeprhythm")
    assert abs(r.bpm - 128) <= 1.0, r
    assert r.beats and 0 < r.confidence <= 1


def test_falls_back_to_librosa_when_torch_missing(click_track, monkeypatch, caplog):
    import djengine.analysis.tempo_deeprhythm as m

    real_import = builtins.__import__

    def no_torch(name, *a, **k):
        if name.startswith(("deeprhythm", "torch")):
            raise ImportError("no torch")
        return real_import(name, *a, **k)

    monkeypatch.setattr(m, "_predictor", None)
    monkeypatch.setattr(builtins, "__import__", no_torch)
    with caplog.at_level(logging.WARNING):
        r = tempo.estimate_tempo(click_track(128), SR, method="deeprhythm")
    assert abs(r.bpm - 128) <= 0.5
    assert "deeprhythm unavailable" in caplog.text


def test_short_clip_falls_back_instead_of_failing(click_track):
    pytest.importorskip("deeprhythm")
    import djengine.analysis.tempo_deeprhythm  # noqa: F401

    r = tempo.estimate_tempo(click_track(128, seconds=5), SR, method="deeprhythm")
    assert abs(r.bpm - 128) <= 1.0


def test_bundled_weights_are_seeded(tmp_path, monkeypatch):
    import djengine.analysis.tempo_deeprhythm as m

    bundled = tmp_path / "models"
    bundled.mkdir()
    (bundled / m.WEIGHTS).write_bytes(b"weights")
    monkeypatch.setenv("ONEFORALL_MODELS", str(bundled))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    target = m.seed_weights()
    assert target.read_bytes() == b"weights"
    assert target.parent == tmp_path / "home" / ".local" / "share" / "deeprhythm"


def test_model_load_failure_falls_back(click_track, monkeypatch):
    import djengine.analysis.tempo_deeprhythm as m

    class Broken:
        def __init__(self, *a, **k):
            raise OSError("no weights offline")

    monkeypatch.setattr(m, "_predictor", None)
    import deeprhythm

    monkeypatch.setattr(deeprhythm, "DeepRhythmPredictor", Broken)
    r = tempo.estimate_tempo(click_track(128, seconds=12), SR, method="deeprhythm")
    assert abs(r.bpm - 128) <= 0.5
