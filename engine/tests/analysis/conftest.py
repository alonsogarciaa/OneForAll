"""Synthetic audio for analysis tests: click tracks and chord progressions with known answers."""
import numpy as np
import pytest
import soundfile as sf

NOTE_INDEX = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def make_click_track(bpm: float, seconds: float = 30, sr: int = 22050) -> np.ndarray:
    y = np.zeros(int(seconds * sr), dtype=np.float32)
    period = 60.0 / bpm
    click = (np.sin(2 * np.pi * 1000 * np.arange(int(0.02 * sr)) / sr) * np.hanning(int(0.02 * sr))).astype(np.float32)
    t = 0.0
    beat = 0
    while t < seconds - 0.05:
        i = int(t * sr)
        amp = 1.0 if beat % 4 == 0 else 0.6
        y[i:i + len(click)] += amp * click[: len(y) - i]
        t += period
        beat += 1
    return y


def _tone(freq: float, n: int, sr: int) -> np.ndarray:
    t = np.arange(n) / sr
    # a few harmonics so chroma looks like an instrument, not a pure sine
    return sum((0.6 ** k) * np.sin(2 * np.pi * freq * (k + 1) * t) for k in range(4))


def make_chord_progression(tonic: str, mode: str, seconds: float = 30, sr: int = 22050) -> np.ndarray:
    """i-iv-v-i (minor, natural) or I-IV-V-I (major) triads, plus the tonic in the bass."""
    root = NOTE_INDEX[tonic]
    scale = [0, 2, 3, 5, 7, 8, 10] if mode == "minor" else [0, 2, 4, 5, 7, 9, 11]
    degrees = [0, 3, 4, 0]
    seg = int(seconds * sr / len(degrees))
    out = []
    for d in degrees:
        notes = [scale[(d + k) % 7] + 12 * ((d + k) // 7) for k in (0, 2, 4)]
        chunk = sum(_tone(220.0 * 2 ** ((root + n - 9) / 12), seg, sr) for n in notes)
        chunk += 0.8 * _tone(110.0 * 2 ** ((root - 9) / 12), seg, sr)  # tonic pedal
        out.append(chunk * np.hanning(seg) ** 0.1)
    y = np.concatenate(out).astype(np.float32)
    return y / np.max(np.abs(y)) * 0.8


@pytest.fixture
def click_track():
    return make_click_track


@pytest.fixture
def chord_progression():
    return make_chord_progression


@pytest.fixture
def write_wav(tmp_path):
    def _write(y: np.ndarray, sr: int, name: str = "a.wav"):
        p = tmp_path / name
        sf.write(p, y.T if y.ndim == 2 else y, sr)
        return p

    return _write
