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

    def split(self, vocals: np.ndarray, sr: int, workdir: Path):
        from audio_separator.separator import Separator

        # audio-separator shells out to "ffmpeg" by name: expose the bundled one on PATH
        tools = str(Path(find_tool("ffmpeg")).parent)
        if tools not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = tools + os.pathsep + os.environ.get("PATH", "")

        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        src = workdir / "karaoke_in.wav"
        sf.write(src, vocals.T, sr, subtype="FLOAT")
        with self._lock:
            try:
                sep = Separator(model_file_dir=str(uvr_dir(self.model_dir)), output_dir=str(workdir), output_format="WAV")
                sep.load_model(model_filename=KARAOKE_MODEL)
                files = sep.separate(str(src))
            except Exception as e:
                log.warning("karaoke model failed: %s", e)
                raise UserError("model_missing", "Falta el modelo de separación y no hay conexión para descargarlo")
        paths = [workdir / Path(f).name for f in files]
        lead = next(p for p in paths if "(Vocals)" in p.name)  # model's primary output: lead vocal
        backing = next(p for p in paths if "(Instrumental)" in p.name)  # what is left of the vocals stem
        out = []
        for p in (lead, backing):
            y, _ = sf.read(p, dtype="float32", always_2d=True)
            y = y.T
            n = vocals.shape[1]
            out.append(y[:, :n] if y.shape[1] >= n else np.pad(y, ((0, 0), (0, n - y.shape[1]))))
        return out[0], out[1]


def get_karaoke(svc, separator):
    if isinstance(separator, FakeSeparator):
        return FakeKaraoke()
    return UvrKaraoke(svc.paths.models_dir / "uvr")
