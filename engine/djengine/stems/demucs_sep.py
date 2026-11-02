"""Demucs htdemucs_6s on the CPU, processed in blocks so progress and cancel work during long songs."""
import logging
import threading
import urllib.error

import numpy as np

from ..errors import JobCancelled, UserError
from .models import ensure_torch_home
from .names import STEMS

log = logging.getLogger(__name__)
MODEL = "htdemucs_6s"
BLOCK_S = 60
FADE_S = 1

try:  # imported here so tests can monkeypatch it
    from demucs.pretrained import get_model
except ImportError:  # pragma: no cover - nn extra missing
    get_model = None


class DemucsSeparator:
    name = MODEL
    _shared: "DemucsSeparator | None" = None
    _shared_lock = threading.Lock()

    def __init__(self):
        self._model = None
        self._lock = threading.Lock()

    @classmethod
    def shared(cls) -> "DemucsSeparator":
        with cls._shared_lock:
            if cls._shared is None:
                cls._shared = cls()
            return cls._shared

    def _load(self):
        with self._lock:
            if self._model is None:
                ensure_torch_home()
                if get_model is None:
                    raise UserError("model_missing", "Falta el modelo de separación y no hay conexión para descargarlo")
                try:
                    model = get_model(MODEL)
                except (urllib.error.URLError, OSError, ConnectionError) as e:
                    log.warning("demucs model unavailable: %s", e)
                    raise UserError("model_missing", "Falta el modelo de separación y no hay conexión para descargarlo")
                model.eval()
                self._model = model
            return self._model

    def separate(self, audio, sr, progress, cancelled):
        import torch
        from demucs.apply import apply_model

        model = self._load()
        n = audio.shape[1]
        block, fade = BLOCK_S * sr, FADE_S * sr
        out = np.zeros((len(model.sources), 2, n), dtype=np.float32)
        weight = np.zeros(n, dtype=np.float32)
        starts = list(range(0, max(n - fade, 1), block - fade)) or [0]
        for i, start in enumerate(starts):
            if cancelled():
                raise JobCancelled()
            end = min(n, start + block)
            seg = torch.from_numpy(np.ascontiguousarray(audio[:, start:end]))[None]
            with torch.no_grad():
                est = apply_model(model, seg, split=True, overlap=0.25, shifts=0, progress=False)[0].numpy()
            # linear cross-fade where consecutive blocks overlap
            w = np.ones(end - start, dtype=np.float32)
            if start > 0:
                w[:fade] = np.linspace(0, 1, fade, dtype=np.float32)
            if end < n:
                w[-fade:] = np.minimum(w[-fade:], np.linspace(1, 0, fade, dtype=np.float32))
            out[:, :, start:end] += est * w
            weight[start:end] += w
            progress((i + 1) / len(starts))
            if end >= n:
                break
        out /= np.maximum(weight, 1e-6)
        by_name = dict(zip(model.sources, out))
        return {s: by_name[s] for s in STEMS}
