import numpy as np
import pyloudnorm as pyln

SILENCE_DB = -120.0


def measure(y_stereo: np.ndarray, sr: int) -> tuple[float | None, float]:
    """Integrated loudness (LUFS, ITU-R BS.1770) and sample peak (dBFS)."""
    data = y_stereo.T if y_stereo.ndim == 2 else y_stereo
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    peak_db = round(20 * np.log10(peak), 2) if peak > 0 else SILENCE_DB
    if peak == 0 or len(data) < int(0.4 * sr):
        return None, peak_db
    lufs = pyln.Meter(sr).integrated_loudness(data)
    return (round(float(lufs), 2) if np.isfinite(lufs) else None), peak_db
