import numpy as np
import pytest

from djengine.analysis.tempo import TEMPO_METHODS, estimate_tempo, fold_bpm

SR = 22050


@pytest.mark.parametrize("bpm,expected", [(128, 128), (64, 128), (174, 174), (90, 90), (100, 100)])
def test_click_tracks(click_track, bpm, expected):
    r = estimate_tempo(click_track(bpm), SR, method="librosa")
    assert abs(r.bpm - expected) <= 0.5, r
    assert r.confidence > 0.3


def test_beats_follow_tempo(click_track):
    r = estimate_tempo(click_track(128), SR)
    gaps = np.diff(r.beats)
    assert len(r.beats) > 40
    assert abs(float(np.median(gaps)) - 60 / 128) < 0.02


def test_fold():
    assert fold_bpm(64) == 128
    assert fold_bpm(200) == 100
    assert fold_bpm(181, hi=180) == 90.5
    assert fold_bpm(35) == 70


def test_silence_does_not_crash():
    r = estimate_tempo(np.zeros(5 * SR, dtype=np.float32), SR)
    assert np.isfinite(r.bpm) and r.confidence < 0.3 and r.beats == []


def test_registry():
    assert "librosa" in TEMPO_METHODS
