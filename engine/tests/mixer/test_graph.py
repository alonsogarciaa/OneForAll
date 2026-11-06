from pathlib import Path

import pytest

from djengine.errors import UserError
from djengine.mixer.graph import build_mix_graph, export_name, output_seconds
from djengine.mixer.state import MixState, StemState

STEMS = {"vocals": Path("C:/s/vocals.wav"), "drums": Path("C:/s/drums.wav")}


def test_identity_has_no_rubberband():
    inputs, fc = build_mix_graph(STEMS, MixState(), "full")
    assert "rubberband" not in fc
    assert "amix=inputs=2:normalize=0:duration=longest" in fc and fc.endswith("[out]")
    assert inputs == ["-i", str(STEMS["vocals"]), "-i", str(STEMS["drums"])]


def test_rate_and_pitch():
    _, fc = build_mix_graph(STEMS, MixState(rate=0.75, stems={"vocals": StemState(semis=2)}), "full")
    assert "rubberband=tempo=0.75:pitch=1.122462:pitchq=quality:transients=mixed" in fc


def test_loop_trims_before_stretch():
    _, fc = build_mix_graph(STEMS, MixState(rate=0.5, loop={"start": 10, "end": 14}), "loop")
    chain = fc.split(";")[0]
    assert "atrim=start=10.000:end=14.000" in chain and chain.index("atrim") < chain.index("rubberband")


def test_muted_and_solo_excluded():
    inputs, fc = build_mix_graph(STEMS, MixState(stems={"vocals": StemState(mute=True)}), "full")
    assert inputs == ["-i", str(STEMS["drums"])] and "amix=inputs=1" in fc
    inputs, _ = build_mix_graph(STEMS, MixState(stems={"vocals": StemState(solo=True)}), "full")
    assert inputs == ["-i", str(STEMS["vocals"])]


def test_nothing_audible_raises():
    with pytest.raises(UserError):
        build_mix_graph(STEMS, MixState(stems={"vocals": StemState(mute=True), "drums": StemState(mute=True)}), "full")


def test_loop_without_loop_raises():
    with pytest.raises(UserError):
        build_mix_graph(STEMS, MixState(), "loop")


def test_paths_never_in_filter():
    odd = {"vocals": Path("C:/s/Don't – DESPECHÁ/vocals.wav")}
    inputs, fc = build_mix_graph(odd, MixState(), "full")
    assert str(odd["vocals"]) in inputs and "DESPECH" not in fc and "Don" not in fc


def test_gain_and_master():
    _, fc = build_mix_graph(STEMS, MixState(master=0.8, stems={"drums": StemState(gain=1.5)}), "full")
    assert "volume=1.500" in fc and "volume=0.800,alimiter=limit=0.99:level=false[out]" in fc


def test_export_names():
    assert export_name(MixState(), "full", "wav") == "mix.wav"
    assert export_name(MixState(rate=0.75, semis=2), "full", "flac") == "mix (0.75x, +2).flac"
    s = MixState(rate=0.75, loop={"start": 72, "end": 88})
    assert export_name(s, "loop", "mp3") == "loop 01m12s-01m28s (0.75x).mp3"
    assert export_name(MixState(semis=-3), "full", "wav") == "mix (-3).wav"


def test_output_seconds():
    assert output_seconds(MixState(rate=0.5, loop={"start": 10, "end": 14}), 200.0, "loop") == 8.0
    assert output_seconds(MixState(rate=0.5), 200.0, "full") == 400.0


def test_output_seconds_loop_past_the_end_is_clamped():
    assert output_seconds(MixState(loop={"start": 190, "end": 210}), 200.0, "loop") == 10.0
