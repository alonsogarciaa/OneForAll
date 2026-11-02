import urllib.error

import numpy as np
import pytest
from scipy.signal import butter, sosfilt

from djengine.errors import UserError

SR = 44100
pytestmark = pytest.mark.slow


def mix(seconds=10):
    n = SR * seconds
    t = np.arange(n) / SR
    bass = 0.4 * np.sin(2 * np.pi * 55 * t)
    clicks = np.zeros(n)
    k = int(0.01 * SR)
    for s in range(0, n - k, SR // 2):
        clicks[s:s + k] += np.random.default_rng(s).normal(0, 0.5, k) * np.hanning(k)
    y = (bass + clicks).astype(np.float32)
    return np.stack([y, y]), bass, clicks


def band_energy(x, kind, f):
    sos = butter(4, f, btype=kind, fs=SR, output="sos")
    return float(np.sum(sosfilt(sos, x) ** 2))


def test_real_htdemucs_6s_splits_drums_and_bass():
    from djengine.stems.demucs_sep import DemucsSeparator
    from djengine.stems.names import STEMS

    audio, bass, clicks = mix()
    steps = []
    out = DemucsSeparator.shared().separate(audio, SR, steps.append, lambda: False)
    assert set(out) == set(STEMS) and all(v.shape == audio.shape for v in out.values())
    assert steps and steps[-1] == pytest.approx(1.0)
    hi = {s: band_energy(out[s][0], "highpass", 3000) for s in STEMS}
    lo = {s: band_energy(out[s][0], "lowpass", 120) for s in STEMS}
    assert hi["drums"] > 0.5 * sum(hi.values())
    assert lo["bass"] > 0.5 * sum(lo.values())


def test_missing_model_offline(monkeypatch):
    import djengine.stems.demucs_sep as m

    def offline(*a, **k):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(m, "get_model", offline)
    with pytest.raises(UserError) as e:
        m.DemucsSeparator()._load()
    assert e.value.code == "model_missing"
