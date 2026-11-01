"""Key from madmom's CNN (Korzeniowski & Widmer 2018). Registers KEY_METHODS["cnn"].

Runs madmom's own pure-Python code (vendored in djengine/vendor, BSD) with the original
model weights (CC BY-NC-SA 4.0: personal, non-commercial use only).
"""
import sys
import threading
from pathlib import Path

import librosa
import numpy as np

from .camelot import to_camelot
from .key import KEY_METHODS, KeyResult

_VENDOR = str(Path(__file__).resolve().parents[1] / "vendor")
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
_lock = threading.Lock()
_proc = None
_labels: list[str] = []
MODEL_SR = 44100


def _processor():
    global _proc, _labels
    with _lock:
        if _proc is None:
            if _VENDOR not in sys.path:
                sys.path.insert(0, _VENDOR)
            from madmom.features.key import KEY_LABELS, CNNKeyRecognitionProcessor

            _proc = CNNKeyRecognitionProcessor()
            _labels = list(KEY_LABELS)
        return _proc


def probabilities(y: np.ndarray, sr: int) -> np.ndarray:
    """24-way key probabilities in madmom's KEY_LABELS order."""
    proc = _processor()
    from madmom.audio.signal import Signal

    if sr != MODEL_SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=MODEL_SR)
    with _lock:
        return np.asarray(proc(Signal(np.ascontiguousarray(y, dtype=np.float32), sample_rate=MODEL_SR))[0])


def cnn_key(y: np.ndarray, sr: int) -> KeyResult:
    if y.size == 0 or float(np.max(np.abs(y))) < 1e-6:
        return KeyResult("C", "major", to_camelot("C", "major"), 0.0)
    p = probabilities(y, sr)
    best = int(np.argmax(p))
    name, mode = _labels[best].split()
    tonic = _FLAT_TO_SHARP.get(name, name)
    return KeyResult(tonic, mode, to_camelot(tonic, mode), round(float(p[best]), 3))


KEY_METHODS["cnn"] = cnn_key
