import numpy as np
from scipy.signal import butter, sosfilt

BANDS = {"low": (None, 250), "mid": (250, 4000), "high": (4000, None)}


def _band(y: np.ndarray, sr: int, lo, hi) -> np.ndarray:
    if lo is None:
        sos = butter(4, hi, btype="lowpass", fs=sr, output="sos")
    elif hi is None:
        sos = butter(4, lo, btype="highpass", fs=sr, output="sos")
    else:
        sos = butter(4, [lo, hi], btype="bandpass", fs=sr, output="sos")
    return sosfilt(sos, y)


def _buckets(x: np.ndarray, n: int, fn) -> np.ndarray:
    edges = np.linspace(0, len(x), n + 1).astype(int)
    out = np.zeros(n)
    for i in range(n):
        seg = x[edges[i]:edges[i + 1]]
        if seg.size:
            out[i] = fn(seg)
    return out


def compute(y: np.ndarray, sr: int, buckets: int = 2000) -> dict[str, list[float]]:
    """Per-bucket peak plus low/mid/high RMS, each normalized to 0..1 (used to colour the waveform)."""
    if y.size == 0 or float(np.max(np.abs(y))) == 0:
        return {k: [0.0] * buckets for k in ("peaks", *BANDS)}
    rms = lambda s: float(np.sqrt(np.mean(s * s)))
    out = {"peaks": _buckets(np.abs(y), buckets, np.max)}
    for name, (lo, hi) in BANDS.items():
        out[name] = _buckets(_band(y, sr, lo, hi), buckets, rms)
    # bands share one scale so their relative energy is kept
    band_max = max(float(out[b].max()) for b in BANDS) or 1.0
    result = {"peaks": out["peaks"] / (float(out["peaks"].max()) or 1.0)}
    for b in BANDS:
        result[b] = out[b] / band_max
    return {k: [round(float(v), 3) for v in arr] for k, arr in result.items()}
