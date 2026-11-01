import logging
from dataclasses import dataclass
from typing import Callable

import librosa
import numpy as np

from .camelot import PITCHES, to_camelot
from .profiles import PROFILES
from .tempo import AnalysisUnavailable

log = logging.getLogger(__name__)


@dataclass
class KeyResult:
    tonic: str
    mode: str
    camelot: str
    confidence: float


def _chroma(y: np.ndarray, sr: int) -> np.ndarray:
    c = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=4096, bins_per_octave=36)
    v = c.mean(axis=1)
    norm = float(np.linalg.norm(v))
    return v / norm if norm > 0 else v


def _profile_key(y: np.ndarray, sr: int, profile: str) -> KeyResult:
    if y.size == 0 or float(np.max(np.abs(y))) < 1e-6:
        return KeyResult("C", "major", to_camelot("C", "major"), 0.0)
    v = _chroma(y, sr)
    scores = []
    for mode in ("major", "minor"):
        prof = np.asarray(PROFILES[profile][mode])
        for tonic in range(12):
            scores.append((float(np.corrcoef(v, np.roll(prof, tonic))[0, 1]), tonic, mode))
    scores.sort(reverse=True)
    best, second = scores[0][0], scores[1][0]
    conf = float(np.clip((best - second) / best, 0.0, 1.0)) if best > 0 else 0.0
    tonic, mode = PITCHES[scores[0][1]], scores[0][2]
    return KeyResult(tonic, mode, to_camelot(tonic, mode), round(max(conf, 1e-3), 3))


KEY_METHODS: dict[str, Callable[[np.ndarray, int], KeyResult]] = {
    name: (lambda y, sr, _n=name: _profile_key(y, sr, _n)) for name in PROFILES
}


def estimate_key(y: np.ndarray, sr: int, method: str = "edma") -> KeyResult:
    fn = KEY_METHODS.get(method, KEY_METHODS["edma"])
    try:
        return fn(y, sr)
    except AnalysisUnavailable as e:
        log.warning("%s unavailable, falling back to edma: %s", method, e)
        return KEY_METHODS["edma"](y, sr)
