"""Apollo restoration by overlapping chunks: progress and cancellation between chunks, crossfaded joins."""
import os
import threading
from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from ..errors import JobCancelled

SR = 44100
CHUNK_S = 10.0
OVERLAP_S = 1.0

Progress = Callable[[float], None]
Cancelled = Callable[[], bool]


def chunks(n: int, sr: int = SR, size_s: float = CHUNK_S, overlap_s: float = OVERLAP_S) -> list[tuple[int, int]]:
    """Spans of `size` samples overlapping by `overlap`; the last one is aligned to the end (never a tiny tail)."""
    size, hop = int(size_s * sr), int((size_s - overlap_s) * sr)
    if n <= 0:
        return []
    if n <= size:
        return [(0, n)]
    spans, start = [], 0
    while start + size < n:
        spans.append((start, start + size))
        start += hop
    spans.append((n - size, n))
    return spans


def stitch(pieces: list[np.ndarray], spans, n: int, overlap: int) -> np.ndarray:
    """Overlap-add with linear fades over each shared region, normalised so the weights always sum to 1."""
    out = np.zeros((pieces[0].shape[0], n), np.float32)
    weight = np.zeros(n, np.float32)
    for i, ((a, b), p) in enumerate(zip(spans, pieces)):
        w = np.ones(b - a, np.float32)
        if i > 0:
            prev_end = spans[i - 1][1]
            k = max(0, prev_end - a)
            if k:
                w[:k] = np.linspace(0, 1, k + 2, dtype=np.float32)[1:-1]
        if i < len(spans) - 1:
            nxt = spans[i + 1][0]
            k = max(0, b - nxt)
            if k:
                w[-k:] = np.minimum(w[-k:], np.linspace(1, 0, k + 2, dtype=np.float32)[1:-1])
        out[:, a:b] += p * w
        weight[a:b] += w
    return out / np.maximum(weight, 1e-8)


def load_audio(path: Path) -> np.ndarray:
    """(2, n) float32 at 44.1 kHz; mono sources are duplicated by ffmpeg (-ac 2)."""
    from ..analysis.audio_io import decode

    return decode(Path(path), sr=SR, mono=False).astype(np.float32, copy=False)


class Restorer(Protocol):
    name: str

    def restore(self, audio: np.ndarray, progress: Progress, cancelled: Cancelled) -> np.ndarray:
        """audio: (2, n) float32 at 44.1 kHz. Raises JobCancelled when cancelled()."""


class _Chunked:
    name = "base"

    def _run(self, x: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def restore(self, audio, progress, cancelled):
        n = audio.shape[1]
        spans = chunks(n)
        if not spans:
            progress(1.0)
            return audio.copy()
        pieces = []
        for i, (a, b) in enumerate(spans):
            if cancelled():
                raise JobCancelled()
            pieces.append(self._run(audio[:, a:b]))
            progress((i + 1) / len(spans))
        return stitch(pieces, spans, n, int(OVERLAP_S * SR))


class FakeRestorer(_Chunked):
    """Identity per chunk: exercises chunking, progress and cancellation without the model."""

    name = "fake"

    def _run(self, x):
        return x.astype(np.float32, copy=True)


class ApolloRestorer(_Chunked):
    name = "apollo"
    _shared: dict = {}
    _lock = threading.Lock()

    def __init__(self, backend: str = "cpu"):
        self.backend = backend
        if backend == "directml":
            import onnxruntime

            from .accel import onnx_dir, ONNX_MODEL

            self._sess = onnxruntime.InferenceSession(
                str(onnx_dir() / ONNX_MODEL), providers=["DmlExecutionProvider", "CPUExecutionProvider"])
            return
        import torch

        from ..vendor.apollo.model import Apollo
        from .models import apollo_path

        torch.set_num_threads(os.cpu_count() or 4)
        from safetensors.torch import load_file

        self._model = Apollo(sr=SR, win=20, feature_dim=256, layer=6)
        self._model.load_state_dict(load_file(str(apollo_path())))
        self._model.eval()

    @classmethod
    def shared(cls, backend: str = "cpu") -> "ApolloRestorer":
        with cls._lock:
            if backend not in cls._shared:
                cls._shared[backend] = cls(backend)
            return cls._shared[backend]

    def _run(self, x):
        size = int(CHUNK_S * SR)
        pad = size - x.shape[1]
        if self.backend == "directml":  # the exported graph has a fixed 10 s input
            xin = np.pad(x, ((0, 0), (0, pad))) if pad > 0 else x
            y = self._sess.run(None, {"audio": xin[None].astype(np.float32)})[0][0]
            return y[:, : x.shape[1]].astype(np.float32)
        import torch

        with torch.inference_mode():
            y = self._model(torch.from_numpy(np.ascontiguousarray(x[None], dtype=np.float32)))
        return y[0].numpy().astype(np.float32)


def get_restorer(svc) -> Restorer:
    if svc.fake or os.environ.get("ONEFORALL_FAKE_ENHANCE") == "1":
        return FakeRestorer()
    from .accel import backend

    return ApolloRestorer.shared(backend(svc.settings))
