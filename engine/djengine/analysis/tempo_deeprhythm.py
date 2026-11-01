"""Tempo from DeepRhythm (CNN, AGPL-3.0, PyTorch CPU). Registers TEMPO_METHODS["deeprhythm"]."""
import logging
import threading

import numpy as np

from .tempo import TEMPO_METHODS, AnalysisUnavailable, TempoResult, beats_for, fold_bpm

log = logging.getLogger(__name__)
_predictor = None
_lock = threading.Lock()


def _get():
    global _predictor
    with _lock:
        if _predictor is None:
            try:
                from deeprhythm import DeepRhythmPredictor
            except ImportError as e:
                raise AnalysisUnavailable(f"deeprhythm unavailable: {e}") from e
            _predictor = DeepRhythmPredictor(device="cpu", quiet=True)
        return _predictor


def deeprhythm_tempo(y: np.ndarray, sr: int, lo: float, hi: float) -> TempoResult:
    if y.size == 0 or float(np.max(np.abs(y))) < 1e-6:
        return TempoResult(0.0, 0.0, [])
    model = _get()
    import torch

    with _lock:  # one inference at a time per process keeps memory flat
        bpm, conf = model.predict_from_audio(torch.from_numpy(np.ascontiguousarray(y)), sr, include_confidence=True)
    bpm = fold_bpm(float(bpm), lo, hi)
    return TempoResult(round(bpm, 1), float(conf), beats_for(y, sr, bpm))


TEMPO_METHODS["deeprhythm"] = deeprhythm_tempo
