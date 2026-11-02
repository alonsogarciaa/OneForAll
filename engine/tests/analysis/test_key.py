import numpy as np
import pytest

from djengine.analysis.key import KEY_METHODS, estimate_key

SR = 22050


@pytest.mark.parametrize("method", ["edma", "temperley", "krumhansl"])
@pytest.mark.parametrize("tonic,mode,code", [("A", "minor", "8A"), ("C", "major", "8B"), ("F#", "minor", "11A"), ("E", "major", "12B")])
def test_progressions(chord_progression, method, tonic, mode, code):
    r = estimate_key(chord_progression(tonic, mode), SR, method=method)
    assert (r.tonic, r.mode, r.camelot) == (tonic, mode, code)
    assert 0 < r.confidence <= 1


def test_silence_gives_zero_confidence():
    r = estimate_key(np.zeros(5 * SR, dtype=np.float32), SR)
    assert r.confidence == 0 and r.camelot is None  # no tonal content: no invented key


def test_registry():
    assert {"edma", "temperley", "krumhansl"} <= set(KEY_METHODS)
