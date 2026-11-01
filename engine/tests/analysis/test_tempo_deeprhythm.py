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
