from bench.metrics import accuracy1, accuracy2, mirex_score, parse_key_label


def test_accuracy1():
    assert accuracy1(126, 128) and accuracy1(133, 128)
    assert not accuracy1(122, 128)


def test_accuracy2_octaves_and_thirds():
    assert accuracy2(64, 128) and accuracy2(256, 128) and accuracy2(43, 128) and accuracy2(384, 128)
    assert not accuracy2(100, 128)


def test_mirex():
    assert mirex_score("8A", "8A") == 1.0
    assert mirex_score("9A", "8A") == 0.5 and mirex_score("7A", "8A") == 0.5
    assert mirex_score("8B", "8A") == 0.3
    assert mirex_score("11B", "8A") == 0.2  # A major vs A minor
    assert mirex_score("5B", "8A") == 0.0


def test_parse_giantsteps_labels():
    assert parse_key_label("C minor") == "5A"
    assert parse_key_label("Eb major") == "5B"
    assert parse_key_label("F# minor") == "11A"
    assert parse_key_label("Bb minor") == "3A"
    assert parse_key_label("-") is None
    assert parse_key_label("Bb minor dorian") == "3A"  # GiantSteps+ adds modal hints
    assert parse_key_label("F maj") is None


def test_summarize_counts_each_reference_separately():
    from bench.run import summarize

    index = [
        {"id": "a", "key": "8A", "bpm_beatport": 128, "bpm_expert": 128},
        {"id": "b", "key": "5A", "bpm_beatport": 174, "bpm_expert": None},
    ]
    preds = {
        "a": {"tempo": {"librosa": 64.0}, "key": {"edma": "8A"}, "secs": {"tempo:librosa": 1, "key:edma": 1}},
        "b": {"tempo": {"librosa": 174.0}, "key": {"edma": "6A"}, "secs": {"tempo:librosa": 1, "key:edma": 1}},
    }
    s = summarize(index, preds, ["librosa"], ["edma"])
    assert s["tempo"]["bpm_beatport"]["librosa"]["n"] == 2
    assert s["tempo"]["bpm_beatport"]["librosa"]["accuracy1"] == 50.0
    assert s["tempo"]["bpm_beatport"]["librosa"]["accuracy2"] == 100.0
    assert s["tempo"]["bpm_expert"]["librosa"]["n"] == 1
    assert s["key"]["edma"]["mirex"] == 0.75
