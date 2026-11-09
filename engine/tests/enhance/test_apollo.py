import subprocess

import numpy as np
import pytest

from djengine.enhance.apollo import FakeRestorer, chunks, load_audio, stitch
from djengine.errors import JobCancelled
from djengine.tools import find_tool

SR = 44100


def test_chunks_cover_everything_with_overlap():
    sp = chunks(SR * 25)
    assert sp[0] == (0, 441000) and sp[-1][1] == SR * 25
    assert all(b[0] == a[1] - SR for a, b in zip(sp[:-2], sp[1:-1]))
    assert sp[-2][1] - sp[-1][0] >= SR  # the end-aligned last chunk overlaps at least 1 s


def test_last_chunk_is_aligned_to_the_end_not_tiny():
    sp = chunks(SR * 10 + 300)
    assert sp[-1] == (300, SR * 10 + 300)
    assert all(b - a == SR * 10 for a, b in sp)


def test_short_song_is_one_chunk():
    assert chunks(SR * 3) == [(0, SR * 3)]
    assert chunks(0) == []


def test_identity_restorer_rebuilds_input():
    x = np.random.default_rng(0).standard_normal((2, SR * 23)).astype(np.float32)
    seen = []
    y = FakeRestorer().restore(x, seen.append, lambda: False)
    assert y.shape == x.shape and np.max(np.abs(y - x)) < 1e-6
    assert seen[-1] == 1.0


def test_tail_shorter_than_overlap():
    x = np.random.default_rng(1).standard_normal((2, SR * 10 + 300)).astype(np.float32)
    y = FakeRestorer().restore(x, lambda p: None, lambda: False)
    assert y.shape == x.shape and np.max(np.abs(y - x)) < 1e-6


def test_stitch_crossfade_has_no_level_step():
    n = SR * 19
    spans = chunks(n)
    pieces = [np.ones((2, b - a), np.float32) for a, b in spans]
    y = stitch(pieces, spans, n, SR)
    assert np.allclose(y, 1.0, atol=1e-6)


def test_cancel_between_chunks():
    x = np.zeros((2, SR * 30), np.float32)
    calls = []
    with pytest.raises(JobCancelled):
        FakeRestorer().restore(x, calls.append, lambda: len(calls) >= 1)
    assert len(calls) == 1


def test_load_audio_48k_mono(tmp_path):
    src = tmp_path / "m.wav"
    subprocess.run([find_tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=3",
                    "-ar", "48000", "-ac", "1", "-y", str(src)], check=True)
    y = load_audio(src)
    assert y.shape[0] == 2 and abs(y.shape[1] - 3 * SR) <= 1
    assert y.dtype == np.float32
