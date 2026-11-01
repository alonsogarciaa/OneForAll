import json
from pathlib import Path

import pytest

from djengine.analysis import config

RESULTS = Path(__file__).resolve().parents[2] / "bench" / "results.json"


def pick(summary):
    tempo = summary["tempo"]["bpm_beatport"]
    t = max(tempo, key=lambda m: (round(tempo[m]["accuracy2"]), tempo[m]["accuracy1"], -tempo[m]["sec_per_track"]))
    key = summary["key"]
    k = max(key, key=lambda m: (key[m]["mirex"], -key[m]["sec_per_track"]))
    return t, k


@pytest.mark.skipif(not RESULTS.exists(), reason="benchmark not run locally")
def test_defaults_are_the_benchmark_winners():
    t, k = pick(json.loads(RESULTS.read_text())["summary"])
    assert (config.DEFAULT_TEMPO_METHOD, config.DEFAULT_KEY_METHOD) == (t, k)


def test_version():
    assert config.ANALYSIS_VERSION == 1
