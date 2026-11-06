"""Song sections on 8-bar phrases: cut where energy, timbre and harmony change, named by energy."""
from dataclasses import asdict, dataclass

import numpy as np

from .grid import Grid

LABELS = ["Intro", "Verso", "Subida", "Estribillo/Drop", "Bajón", "Outro"]
COLORS: dict[str, tuple[int, int, int]] = {
    "Intro": (142, 142, 147),
    "Verso": (10, 132, 255),
    "Subida": (255, 214, 10),
    "Estribillo/Drop": (255, 69, 58),
    "Bajón": (191, 90, 242),
    "Outro": (99, 99, 102),
}
PHRASE_BARS = 8
MAX_SECTIONS = 16
KERNEL_BARS = 8  # Foote checkerboard size (4 bars each side)
HOP = 512


@dataclass
class Section:
    start: float
    end: float
    label: str
    source: str = "auto"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Section":
        return cls(float(d["start"]), float(d["end"]), str(d["label"]), d.get("source", "auto"))


def label_sections(energies: list[float]) -> list[str]:
    """Names from relative energy and position (spec §4), applied in order."""
    n = len(energies)
    if n == 0:
        return []
    e = np.asarray(energies, dtype=float)
    med = float(np.median(e))
    p70 = float(np.percentile(e, 70))
    high = [bool(v > p70) for v in e]
    out = [""] * n
    for i in range(n):
        if i == 0 and e[i] < med:
            out[i] = "Intro"
        elif i == n - 1 and n > 1 and e[i] < med:
            out[i] = "Outro"
        elif high[i]:
            out[i] = "Estribillo/Drop"
        elif i > 0 and high[i - 1] and e[i] < 0.5 * e[i - 1]:  # a clear drop after a high part
            out[i] = "Bajón"
        elif 0 < i < n - 1 and e[i] > e[i - 1] and high[i + 1]:
            out[i] = "Subida"
        else:
            out[i] = "Verso"
    return out


def _bar_features(y: np.ndarray, sr: int, bars: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    import librosa

    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=HOP)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=HOP)
    frames = np.clip((bars * sr / HOP).astype(int), 0, rms.size)
    feats, energy = [], []
    for a, b in zip(frames[:-1], frames[1:]):
        b = max(b, a + 1)
        feats.append(np.concatenate([[rms[a:b].mean()], mfcc[:, a:b].mean(axis=1), chroma[:, a:b].mean(axis=1)]))
        energy.append(float(rms[a:b].mean()))
    f = np.asarray(feats)
    f = (f - f.mean(axis=0)) / (f.std(axis=0) + 1e-9)
    # each group (energy, timbre, harmony) weighs the same in the distance
    f[:, 0] *= np.sqrt(13)
    f[:, 14:] *= np.sqrt(13 / 12)
    return f, np.asarray(energy)


def _novelty(f: np.ndarray) -> np.ndarray:
    d = np.square(f[:, None, :] - f[None, :, :]).sum(axis=2)
    s = np.exp(-d / (np.median(d[d > 0]) + 1e-9)) if np.any(d > 0) else np.ones_like(d)
    h = KERNEL_BARS // 2
    g = np.outer(np.r_[-np.ones(h), np.ones(h)], np.r_[-np.ones(h), np.ones(h)])  # +1 within a side, -1 across
    taper = np.outer(np.hanning(2 * h + 2)[1:-1], np.hanning(2 * h + 2)[1:-1])
    k = g * taper
    pad = np.pad(s, h, mode="edge")
    n = len(f)
    return np.array([float((pad[i:i + 2 * h, i:i + 2 * h] * k).sum()) for i in range(n)])


def detect_sections(y: np.ndarray, sr: int, grid: Grid, duration: float) -> list[Section]:
    if not grid.bpm or grid.bpm <= 0 or duration <= 0 or y.size == 0 or float(np.abs(y).max()) < 1e-4:
        return []
    bar = 4 * 60.0 / grid.bpm
    j0 = int(np.ceil(-grid.anchor / bar - 1e-9))
    starts = [grid.anchor + j * bar for j in range(j0, int((duration - grid.anchor) / bar) + 1)]
    bars = np.asarray([0.0] + [t for t in starts if 1e-6 < t < duration] + [duration])
    n_bars = len(bars) - 1
    if n_bars < 2 * PHRASE_BARS:
        return [Section(0.0, round(duration, 3), label_sections([1.0])[0])]
    f, bar_energy = _bar_features(y, sr, bars)
    nov = _novelty(f)
    # candidate cuts: bars that start an 8-bar phrase counted from the anchor
    cands = [i for i in range(1, n_bars) if round((bars[i] - grid.anchor) / bar) % PHRASE_BARS == 0
             and abs((bars[i] - grid.anchor) / bar - round((bars[i] - grid.anchor) / bar)) < 1e-6]
    if not cands:
        return [Section(0.0, round(duration, 3), "Verso")]
    top = max(nov[i] for i in cands)
    keep = sorted([i for i in cands if top > 0 and nov[i] >= 0.25 * top], key=lambda i: -nov[i])[: MAX_SECTIONS - 1]
    cuts = sorted(keep)
    edges = [0] + cuts + [n_bars]
    energies = [float(bar_energy[a:b].mean()) for a, b in zip(edges[:-1], edges[1:])]
    peak = max(energies) or 1.0
    labels = label_sections([e / peak for e in energies])
    return [Section(round(float(bars[a]), 3), round(float(bars[b]), 3), lab)
            for (a, b), lab in zip(zip(edges[:-1], edges[1:]), labels)]
