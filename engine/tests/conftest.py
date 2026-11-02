import pytest
from fastapi.testclient import TestClient

from djengine.app_paths import AppPaths
from djengine.server import build_services, create_app


@pytest.fixture
def paths(tmp_path):
    return AppPaths.from_root(tmp_path / "data")


@pytest.fixture
def client(paths):
    return TestClient(create_app(build_services(paths, fake=True), token="t"))


# --- shared helpers for audio tests ---------------------------------------
import os
import subprocess
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[2] / "build" / "runtime" / "bin"
if _TOOLS.is_dir() and "ONEFORALL_TOOLS" not in os.environ:
    os.environ["ONEFORALL_TOOLS"] = str(_TOOLS)


class FakeCtx:
    """Stand-in for JobContext in unit tests: records progress, never cancelled unless told."""

    def __init__(self, tmp_dir: Path):
        self.tmp_dir = tmp_dir
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.reports: list[tuple] = []
        self.processes = []
        self.cancelled = False
        self.finishing = False

    def report(self, stage, pct, speed=None, eta=None):
        self.reports.append((stage, pct, speed, eta))

    def register_process(self, proc):
        self.processes.append(proc)

    def check_cancelled(self):
        from djengine.errors import JobCancelled

        if self.cancelled:
            raise JobCancelled()

    def begin_finalize(self):
        self.check_cancelled()
        self.finishing = True


@pytest.fixture
def ctx(tmp_path):
    return FakeCtx(tmp_path / "job")


@pytest.fixture(scope="session")
def sine_wav(tmp_path_factory):
    from djengine.tools import find_tool

    out = tmp_path_factory.mktemp("audio") / "sine.wav"
    subprocess.run(
        [find_tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=3", "-ac", "2", str(out)],
        check=True,
    )
    return out


@pytest.fixture
def click_track_file():
    """Writes a 20 s, 128 BPM click track to the given path."""
    import numpy as np
    import soundfile as sf

    def make(path, bpm=128, seconds=20, sr=44100):
        y = np.zeros(int(seconds * sr), dtype=np.float32)
        n = int(0.02 * sr)
        click = (np.sin(2 * np.pi * 1000 * np.arange(n) / sr) * np.hanning(n)).astype(np.float32)
        t = 0.0
        while t < seconds - 0.05:
            i = int(t * sr)
            y[i:i + n] += click[: len(y) - i]
            t += 60.0 / bpm
        sf.write(path, y, sr)
        return path

    return make
