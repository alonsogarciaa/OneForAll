"""Key from madmom's CNN (Korzeniowski & Widmer 2018). Registers KEY_METHODS["cnn"].

Runs madmom's own pure-Python code (vendored in djengine/vendor, BSD) with the original
model weights (CC BY-NC-SA 4.0: personal, non-commercial use only).
"""
import logging
import sys
import threading
from pathlib import Path

import librosa
import numpy as np

from .camelot import to_camelot
from .key import KEY_METHODS, NO_KEY, KeyResult

log = logging.getLogger(__name__)
_VENDOR = str(Path(__file__).resolve().parents[1] / "vendor")
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
_lock = threading.Lock()
_proc = None
_labels: list[str] = []
MODEL_SR = 44100


def _use_vendored_madmom() -> None:
    """Make "import madmom" resolve to our vendored copy, even if a pip madmom was imported first."""
    mod = sys.modules.get("madmom")
    if mod is not None and not str(getattr(mod, "__file__", "") or "").startswith(_VENDOR):
        log.warning("a different madmom was already imported (%s): switching to the vendored one", mod.__file__)
        for name in [n for n in sys.modules if n == "madmom" or n.startswith("madmom.")]:
            del sys.modules[name]
    if _VENDOR in sys.path:
        sys.path.remove(_VENDOR)
    sys.path.insert(0, _VENDOR)


def _processor():
    global _proc, _labels
    with _lock:
        if _proc is None:
            _use_vendored_madmom()
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
        return NO_KEY
    p = probabilities(y, sr)
    if not np.isfinite(p).all():  # clips under ~1.5 s give NaN: use the template method instead
        return KEY_METHODS["edma"](y, sr)
    best = int(np.argmax(p))
    name, mode = _labels[best].split()
    tonic = _FLAT_TO_SHARP.get(name, name)
    return KeyResult(tonic, mode, to_camelot(tonic, mode), round(float(p[best]), 3))


KEY_METHODS["cnn"] = cnn_key
