import numpy as np
import pytest

from djengine.analysis.audio_io import decode
from djengine.analysis.camelot import compatible, display_key, from_camelot, tag_key, to_camelot
from djengine.errors import UserError

WHEEL = {
    "1A": ("G#", "minor"), "2A": ("D#", "minor"), "3A": ("A#", "minor"), "4A": ("F", "minor"),
    "5A": ("C", "minor"), "6A": ("G", "minor"), "7A": ("D", "minor"), "8A": ("A", "minor"),
    "9A": ("E", "minor"), "10A": ("B", "minor"), "11A": ("F#", "minor"), "12A": ("C#", "minor"),
    "1B": ("B", "major"), "2B": ("F#", "major"), "3B": ("C#", "major"), "4B": ("G#", "major"),
    "5B": ("D#", "major"), "6B": ("A#", "major"), "7B": ("F", "major"), "8B": ("C", "major"),
    "9B": ("G", "major"), "10B": ("D", "major"), "11B": ("A", "major"), "12B": ("E", "major"),
}


@pytest.mark.parametrize("code,key", WHEEL.items())
def test_wheel_roundtrip(code, key):
    assert to_camelot(*key) == code
    assert from_camelot(code) == key


def test_display_and_tags():
    assert display_key("F#", "minor") == "11A · Fa#m"
    assert display_key("C", "major") == "8B · Do"
    assert tag_key("A", "minor", "musical") == "Am"
    assert tag_key("F#", "major", "musical") == "F#"
    assert tag_key("A", "minor", "camelot") == "8A"


@pytest.mark.parametrize("a,b,level", [
    ("8A", "8A", "same"), ("8A", "9A", "adjacent"), ("8A", "7A", "adjacent"),
    ("12A", "1A", "adjacent"), ("1B", "12B", "adjacent"), ("8A", "8B", "relative"),
    ("8A", "10A", None), ("8A", "9B", None),
])
def test_compatibility(a, b, level):
    assert compatible(a, b) == level


def test_decode_stereo_wav_to_mono(write_wav):
    sr = 22050
    t = np.arange(3 * sr) / sr
    y = np.stack([0.5 * np.sin(2 * np.pi * 440 * t), 0.5 * np.sin(2 * np.pi * 440 * t)]).astype(np.float32)
    out = decode(write_wav(y, sr), sr=sr)
    assert out.ndim == 1 and abs(len(out) - 3 * sr) < sr * 0.01
    assert 0.45 < float(np.max(np.abs(out))) < 0.75  # ffmpeg downmix sums channels at -3 dB


def test_decode_stereo_keeps_channels(write_wav):
    sr = 44100
    y = np.zeros((2, sr), dtype=np.float32)
    assert decode(write_wav(y, sr), sr=sr, mono=False).shape[0] == 2


def test_decode_garbage_raises(tmp_path):
    bad = tmp_path / "x.mp3"
    bad.write_text("not audio")
    with pytest.raises(UserError) as e:
        decode(bad)
    assert e.value.code == "unreadable"
