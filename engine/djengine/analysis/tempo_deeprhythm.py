"""Tempo from DeepRhythm (CNN, AGPL-3.0, PyTorch CPU). Registers TEMPO_METHODS["deeprhythm"]."""
import logging
import os
import shutil
import threading
from pathlib import Path

import numpy as np

from .tempo import TEMPO_METHODS, AnalysisUnavailable, TempoResult, beats_for, fold_bpm, librosa_tempo

log = logging.getLogger(__name__)
_predictor = None
WEIGHTS = "deeprhythm-0.7.pth"  # file name deeprhythm.utils.get_weights expects
MIN_SECONDS = 8.5  # DeepRhythm works on 8 s clips; shorter audio yields no clip at all
_lock = threading.Lock()


def seed_weights() -> Path:
    """Copy the bundled weights to where deeprhythm looks, so the first analysis works offline."""
    target = Path(os.path.expanduser("~")) / ".local" / "share" / "deeprhythm" / WEIGHTS
    bundled = os.environ.get("ONEFORALL_MODELS")
    if bundled and not target.exists() and (Path(bundled) / WEIGHTS).is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(bundled) / WEIGHTS, target)
    return target


def _get():
    global _predictor
    with _lock:
        if _predictor is None:
            try:
                from deeprhythm import DeepRhythmPredictor
            except ImportError as e:
                raise AnalysisUnavailable(f"deeprhythm unavailable: {e}") from e
            seed_weights()
            try:
                _predictor = DeepRhythmPredictor(device="cpu", quiet=True)
            except Exception as e:  # e.g. weights missing and no internet
                raise AnalysisUnavailable(f"deeprhythm model could not load: {e}") from e
        return _predictor


def deeprhythm_tempo(y: np.ndarray, sr: int, lo: float, hi: float) -> TempoResult:
    if y.size == 0 or float(np.max(np.abs(y))) < 1e-6:
        return TempoResult(0.0, 0.0, [])
    if len(y) < MIN_SECONDS * sr:
        return librosa_tempo(y, sr, lo, hi)
    model = _get()
    import torch

    with _lock:  # one inference at a time per process keeps memory flat
        bpm, conf = model.predict_from_audio(torch.from_numpy(np.ascontiguousarray(y)), sr, include_confidence=True)
    bpm = fold_bpm(float(bpm), lo, hi)
    return TempoResult(round(bpm, 1), float(conf), beats_for(y, sr, bpm))


TEMPO_METHODS["deeprhythm"] = deeprhythm_tempo
