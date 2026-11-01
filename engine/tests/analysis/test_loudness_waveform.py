import numpy as np
import pyloudnorm as pyln

from djengine.analysis.loudness import measure
from djengine.analysis.waveform import compute


def sine(freq, seconds, sr, amp):
    t = np.arange(int(seconds * sr)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_loudness_matches_pyloudnorm_and_peak():
    sr = 44100
    m = sine(1000, 10, sr, 10 ** (-20 / 20))
    y = np.stack([m, m])
    lufs, peak = measure(y, sr)
    ref = pyln.Meter(sr).integrated_loudness(y.T)
    assert abs(peak - (-20.0)) < 0.1
    assert abs(lufs - ref) < 0.05 and -24 < lufs < -18


def test_silence_has_no_lufs():
    lufs, peak = measure(np.zeros((2, 44100 * 3), dtype=np.float32), 44100)
    assert lufs is None and peak == -120.0


def test_waveform_bands_and_length():
    sr = 22050
    w = compute(sine(80, 5, sr, 0.8), sr, buckets=500)
    assert set(w) == {"peaks", "low", "mid", "high"} and all(len(v) == 500 for v in w.values())
    assert np.mean(w["low"]) > 3 * np.mean(w["high"])
    assert max(w["peaks"]) <= 1.0


def test_waveform_silence_and_long_file():
    sr = 22050
    assert compute(np.zeros(sr, dtype=np.float32), sr)["peaks"] == [0.0] * 2000
    assert len(compute(np.zeros(sr * 600, dtype=np.float32), sr)["peaks"]) == 2000
