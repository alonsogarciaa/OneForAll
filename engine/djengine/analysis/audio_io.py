import subprocess
from pathlib import Path

import numpy as np

from ..errors import UserError
from ..tools import find_tool


def decode(path: Path, sr: int = 22050, mono: bool = True) -> np.ndarray:
    """Decode any audio file with ffmpeg to float32: shape (n,) for mono, (2, n) for stereo."""
    channels = 1 if mono else 2
    proc = subprocess.run(
        [find_tool("ffmpeg"), "-v", "error", "-nostdin", "-i", str(path), "-vn",
         "-f", "f32le", "-ac", str(channels), "-ar", str(sr), "pipe:1"],
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise UserError("unreadable", "No se puede leer el audio de este archivo")
    y = np.frombuffer(proc.stdout, dtype=np.float32)
    if mono:
        return y.copy()
    return y.reshape(-1, 2).T.copy()
