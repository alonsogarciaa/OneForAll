import logging
from dataclasses import dataclass, field
from typing import Callable

import librosa
import numpy as np

log = logging.getLogger(__name__)

HOP = 256


@dataclass
class TempoResult:
    bpm: float
    confidence: float
    beats: list[float] = field(default_factory=list)


class AnalysisUnavailable(RuntimeError):
    """A method's dependencies are missing; callers fall back to librosa."""


def fold_bpm(bpm: float, lo: float = 70, hi: float = 180) -> float:
    """Double or halve until the tempo sits in the DJ range (64 -> 128, 200 -> 100)."""
    if bpm <= 0:
        return bpm
    while bpm < lo:
        bpm *= 2
    while bpm > hi:
        bpm /= 2
    return round(bpm, 2)


def _onset_env(y: np.ndarray, sr: int) -> np.ndarray:
    return librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)


def _comb_score(env: np.ndarray, bpm: float, sr: int) -> float:
    """How well a pulse train at `bpm` (best phase) lines up with the onset envelope."""
    period = 60.0 * sr / (HOP * bpm)
    n = int((len(env) - 1) / period)
    if n < 4:
        return 0.0
    k = np.arange(n) * period
    phases = np.arange(0, period, 1.0)
    pos = phases[:, None] + k[None, :]
    vals = np.interp(pos, np.arange(len(env)), env)
    return float(vals.mean(axis=1).max())


def _refine(env: np.ndarray, sr: int, bpm: float) -> float:
    """Search ±2 BPM in 0.05 steps for the best-aligned pulse train, for 0.1 BPM precision."""
    grid = np.arange(bpm - 2.0, bpm + 2.0001, 0.05)
    scores = [_comb_score(env, b, sr) for b in grid]
    return float(grid[int(np.argmax(scores))])


def _confidence(env: np.ndarray, sr: int, bpm: float) -> float:
    x = env - env.mean()
    ac = librosa.autocorrelate(x)
    if ac[0] <= 0:
        return 0.0
    # Periodicity at the octave (half/double) is still evidence for a folded tempo.
    best = 0.0
    for b in (bpm, bpm / 2, bpm * 2):
        lag = int(round(60.0 * sr / (HOP * b)))
        if 1 <= lag < len(ac):
            best = max(best, float(ac[max(1, lag - 2): lag + 3].max()))
    return float(np.clip(best / ac[0], 0.0, 1.0))


def _beats(env: np.ndarray, sr: int, bpm: float) -> list[float]:
    _, beats = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=HOP, bpm=bpm, units="time", tightness=200)
    return [round(float(b), 3) for b in beats]


def librosa_tempo(y: np.ndarray, sr: int, lo: float, hi: float) -> TempoResult:
    env = _onset_env(y, sr)
    if env.size == 0 or float(env.max()) < 1e-6:
        return TempoResult(0.0, 0.0, [])
    raw = float(librosa.feature.tempo(onset_envelope=env, sr=sr, hop_length=HOP, aggregate=np.mean)[0])
    bpm = fold_bpm(_refine(env, sr, fold_bpm(raw, lo, hi)), lo, hi)
    return TempoResult(round(bpm, 1), _confidence(env, sr, bpm), _beats(env, sr, bpm))


TEMPO_METHODS: dict[str, Callable[[np.ndarray, int, float, float], TempoResult]] = {"librosa": librosa_tempo}


def beats_for(y: np.ndarray, sr: int, bpm: float) -> list[float]:
    """Beat grid from librosa aligned to a tempo chosen by any method."""
    env = _onset_env(y, sr)
    if env.size == 0 or float(env.max()) < 1e-6:
        return []
    return _beats(env, sr, bpm)


def estimate_tempo(y: np.ndarray, sr: int, method: str = "librosa", lo: float = 70, hi: float = 180) -> TempoResult:
    fn = TEMPO_METHODS.get(method, librosa_tempo)
    try:
        return fn(y, sr, lo, hi)
    except AnalysisUnavailable as e:
        log.warning("%s unavailable, falling back to librosa: %s", method, e)
        return librosa_tempo(y, sr, lo, hi)
