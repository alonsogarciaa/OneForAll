"""Lead / backing vocal split of the vocals stem (UVR-MDX-NET Karaoke 2, ONNX via audio-separator)."""
import logging
import os
import threading
from pathlib import Path

import numpy as np
import soundfile as sf

from ..errors import UserError
from ..tools import find_tool
from .models import uvr_dir
from .separate import FakeSeparator

log = logging.getLogger(__name__)
KARAOKE_MODEL = "UVR_MDXNET_KARA_2.onnx"


class FakeKaraoke:
    """Mid = lead, side = backing: instant, for tests and --fake mode."""

    def split(self, vocals: np.ndarray, sr: int, workdir: Path):
        mid = (vocals[0] + vocals[1]) / 2
        side = (vocals[0] - vocals[1]) / 2
        return np.stack([mid, mid]), np.stack([side, -side])


class UvrKaraoke:
    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir)
        self._lock = threading.Lock()
        self._sep = None  # loaded once, reused by every job

    def split(self, vocals: np.ndarray, sr: int, workdir: Path):
        from audio_separator.separator import Separator


        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        src = workdir / "karaoke_in.wav"
        sf.write(src, vocals.T, sr, subtype="FLOAT")
        with self._lock:
            try:
                if self._sep is None:
                    self._sep = Separator(model_file_dir=str(uvr_dir(self.model_dir)), output_dir=str(workdir), output_format="WAV")
                    self._sep.load_model(model_filename=KARAOKE_MODEL)
                self._sep.output_dir = str(workdir)
                if hasattr(self._sep, "model_instance") and self._sep.model_instance is not None:
                    self._sep.model_instance.output_dir = str(workdir)
                files = self._sep.separate(str(src))
            except Exception as e:
                log.warning("karaoke model failed: %s", e)
                raise UserError("model_missing", "Falta el modelo de separación y no hay conexión para descargarlo")
        paths = [workdir / Path(f).name for f in files]
        lead = next((p for p in paths if "(Vocals)" in p.name), None)  # model's primary output: lead vocal
        backing = next((p for p in paths if "(Instrumental)" in p.name), None)  # what is left of the vocals stem
        if lead is None or backing is None:
            log.warning("unexpected karaoke outputs: %s", [p.name for p in paths])
            raise UserError("internal", "La separación de voces no generó los archivos esperados")
        out = []
        for p in (lead, backing):
            y, _ = sf.read(p, dtype="float32", always_2d=True)
            y = y.T
            n = vocals.shape[1]
            out.append(y[:, :n] if y.shape[1] >= n else np.pad(y, ((0, 0), (0, n - y.shape[1]))))
        return out[0], out[1]


_shared: dict[str, UvrKaraoke] = {}
_shared_lock = threading.Lock()


def get_karaoke(svc, separator):
    if isinstance(separator, FakeSeparator):
        return FakeKaraoke()
    d = str(svc.paths.models_dir / "uvr")
    with _shared_lock:
        if d not in _shared:
            _shared[d] = UvrKaraoke(Path(d))
        return _shared[d]
