"""Fixed beat grid, as DJ software stores it: the first "1" (anchor) plus a constant BPM."""
import math
from dataclasses import asdict, dataclass, replace

import numpy as np


@dataclass
class Grid:
    anchor: float  # seconds of a bar's first beat
    bpm: float
    source: str = "auto"  # "auto" | "manual"
    meter: int = 4

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Grid":
        return cls(float(d["anchor"]), float(d["bpm"]), d.get("source", "auto"), int(d.get("meter", 4)))


def beats(grid: Grid, duration: float) -> list[float]:
    """Every beat of the grid inside [0, duration), including the ones before the anchor."""
    if not grid.bpm or grid.bpm <= 0 or duration <= 0:
        return []
    p = 60.0 / grid.bpm
    k = math.ceil(-grid.anchor / p - 1e-9)
    out = []
    while True:
        t = grid.anchor + k * p
        if t >= duration - 1e-9:
            return out
        if t >= -1e-9:
            out.append(round(max(t, 0.0), 4))
        k += 1


def grid_from_beats(detected: list[float], bpm: float) -> Grid:
    """Phase that best fits the detected beats (circular mean); anchor = first grid point >= 0."""
    if not detected or not bpm or bpm <= 0:
        return Grid(0.0, float(bpm or 0))
    p = 60.0 / bpm
    ang = np.array([2 * math.pi * (b % p) / p for b in detected])
    phase = (math.atan2(np.sin(ang).mean(), np.cos(ang).mean()) % (2 * math.pi)) / (2 * math.pi) * p
    return Grid(round(float(phase), 4), float(bpm))


def estimate_grid(y: np.ndarray, sr: int, bpm: float, detected: list[float]) -> Grid:
    """Grid phase from the detected beats; the "1" is the grid point (of the first 8) with the most bass attack."""
    g = grid_from_beats(detected, bpm)
    if not g.bpm or y.size == 0:
        return g
    import librosa

    hop = 512
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop, fmax=150, n_mels=16)
    if env.size == 0 or float(env.max()) < 1e-9:
        return g
    p = 60.0 / g.bpm
    # bass attack summed by bar position over the first 32 beats: the strongest position is the "1"
    sums = [0.0] * g.meter
    for k in range(32):
        f = int(round((g.anchor + k * p) * sr / hop))
        if f >= env.size:
            break
        sums[k % g.meter] += float(env[max(0, f - 2): f + 3].max())
    if max(sums) <= 0:
        return g
    pos = sums.index(max(sums))
    return Grid(round(g.anchor + pos * p, 4), g.bpm)


def edit_grid(grid: Grid, *, anchor=None, bpm=None, shift_ms=None, shift_beats=None, scale=None) -> Grid:
    """One user edit; the result is always a manual grid."""
    g = replace(grid, source="manual")
    if bpm is not None:
        g.bpm = float(bpm)
    if scale is not None:
        g.bpm = g.bpm * float(scale)
    if anchor is not None:
        g.anchor = float(anchor)
    if shift_ms is not None:
        g.anchor = g.anchor + float(shift_ms) / 1000.0
    if shift_beats is not None and g.bpm > 0:
        g.anchor = g.anchor + int(shift_beats) * 60.0 / g.bpm
    g.anchor = round(g.anchor, 4)
    return g
