import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from djengine.analysis.key import estimate_key

ROOT = Path(__file__).resolve().parents[2]
REF = json.loads((ROOT / "tests" / "fixtures" / "cnn_key_reference.json").read_text())
WAVS = ROOT / "bench" / "data" / "ref"


def test_cnn_on_chord_progression(chord_progression):
    import djengine.analysis.key_cnn  # noqa: F401  (registers "cnn")

    r = estimate_key(chord_progression("A", "minor"), 22050, method="cnn")
    # Synthetic sine chords are outside what the CNN was trained on (real recordings): only the
    # tonic is checked here. Correctness is pinned by test_matches_compiled_madmom and the benchmark.
    assert r.tonic == "A" and 0 < r.confidence <= 1


@pytest.mark.skipif(not WAVS.exists(), reason="benchmark clips not downloaded (python -m bench.fetch_giantsteps)")
@pytest.mark.parametrize("clip", sorted(REF))
def test_matches_compiled_madmom(clip):
    """Vendored pure-Python madmom must give the same probabilities as compiled madmom (WSL)."""
    from djengine.analysis.key_cnn import probabilities

    y, sr = sf.read(WAVS / f"{clip}.wav", dtype="float32")
    p = probabilities(y, sr)
    ref = np.asarray(REF[clip])
    assert int(np.argmax(p)) == int(np.argmax(ref))
    assert np.max(np.abs(p - ref)) < 1e-3
