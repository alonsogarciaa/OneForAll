"""Separator protocol and the fast fake used by tests and --fake mode."""
from typing import Callable, Protocol

import numpy as np
from scipy.signal import butter, sosfilt

from ..errors import JobCancelled
from .names import STEMS

Progress = Callable[[float], None]
Cancelled = Callable[[], bool]


class Separator(Protocol):
    name: str

    def separate(self, audio: np.ndarray, sr: int, progress: Progress, cancelled: Cancelled) -> dict[str, np.ndarray]:
        """audio: (2, n) float32. Returns all STEMS as (2, n) arrays. Raises JobCancelled when cancelled()."""


def _filt(y: np.ndarray, sr: int, kind: str, f) -> np.ndarray:
    sos = butter(4, f, btype=kind, fs=sr, output="sos")
    return sosfilt(sos, y, axis=-1).astype(np.float32)


class FakeSeparator:
    """Deterministic filters standing in for Demucs: fast, so tests and --fake mode stay quick."""

    name = "fake"

    def separate(self, audio, sr, progress, cancelled):
        out = {}
        plan = {
            "bass": ("lowpass", 150), "drums": ("highpass", 5000), "vocals": ("bandpass", [300, 3000]),
            "guitar": ("bandpass", [200, 1200]), "piano": ("bandpass", [250, 4000]), "other": ("bandpass", [100, 8000]),
        }
        for i, stem in enumerate(STEMS):
            if cancelled():
                raise JobCancelled()
            kind, f = plan[stem]
            out[stem] = _filt(audio, sr, kind, f)
            progress((i + 1) / len(STEMS))
        return out


def get_separator(svc) -> Separator:
    import os

    if svc.fake or os.environ.get("ONEFORALL_FAKE_STEMS") == "1":
        return FakeSeparator()
    from .demucs_sep import DemucsSeparator  # Task 3

    return DemucsSeparator.shared()
