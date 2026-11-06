import numpy as np

from djengine.prep.grid import Grid
from djengine.prep.sections import COLORS, LABELS, Section, detect_sections, label_sections

SR = 22050
BPM = 128.0
BAR = 4 * 60.0 / BPM


def _tone(freqs, seconds, amp):
    t = np.arange(int(seconds * SR)) / SR
    return (amp * sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)).astype(np.float32)


def _part(bars, loud, rng):
    n = int(bars * BAR * SR)
    y = np.zeros(n, dtype=np.float32)
    beat = int(60.0 / BPM * SR)
    if loud == "hat":
        for i in range(0, n, beat // 2):
            m = min(400, n - i)
            y[i:i + m] += 0.05 * rng.standard_normal(m).astype(np.float32)
    elif loud == "drop":
        kick = _tone([60], 0.12, 0.9) * np.hanning(int(0.12 * SR)).astype(np.float32)
        for i in range(0, n - len(kick), beat):
            y[i:i + len(kick)] += kick
        y += _tone([55], n / SR, 0.35)[:n]
        y += _tone([220, 277, 330], n / SR, 0.3)[:n]
    elif loud == "pads":
        y += _tone([440, 554], n / SR, 0.08)[:n]
    return y


def _song():
    rng = np.random.default_rng(1)
    parts = [(8, "hat"), (16, "drop"), (8, "pads"), (16, "drop"), (8, "hat")]
    return np.concatenate([_part(b, kind, rng) for b, kind in parts])


def test_label_rules():
    assert label_sections([0.2, 0.5, 0.7, 1.0, 0.3, 0.9, 0.1]) == [
        "Intro", "Verso", "Subida", "Estribillo/Drop", "Bajón", "Estribillo/Drop", "Outro"]


def test_labels_and_colors_are_fixed():
    assert LABELS == ["Intro", "Verso", "Subida", "Estribillo/Drop", "Bajón", "Outro"]
    assert COLORS["Estribillo/Drop"] == (255, 69, 58) and COLORS["Intro"] == (142, 142, 147)


def test_detects_synthetic_structure():
    y = _song()
    secs = detect_sections(y, SR, Grid(0.0, BPM), len(y) / SR)
    starts = [round(s.start / BAR) for s in secs[1:]]
    assert len(starts) == 4 and all(abs(a - b) <= 1 for a, b in zip(starts, [8, 24, 32, 48])), starts
    assert [s.label for s in secs] == ["Intro", "Estribillo/Drop", "Bajón", "Estribillo/Drop", "Outro"]
    assert secs[0].start == 0 and abs(secs[-1].end - len(y) / SR) < 1e-6


def test_boundaries_on_8_bar_multiples():
    y = _song()
    for s in detect_sections(y, SR, Grid(0.0, BPM), len(y) / SR)[1:]:
        k = s.start / (8 * BAR)
        assert abs(k - round(k)) * 8 * BAR < 0.001


def test_short_or_silent_track():
    short = _tone([440], 10, 0.3)
    assert len(detect_sections(short, SR, Grid(0.0, BPM), 10.0)) <= 1
    silent = np.zeros(SR * 60, dtype=np.float32)
    assert detect_sections(silent, SR, Grid(0.0, BPM), 60.0) == []
    assert detect_sections(short, SR, Grid(0.0, 0.0), 10.0) == []  # no beats at all


def test_at_most_16_sections():
    rng = np.random.default_rng(2)
    chunks = []
    for i in range(300 // 8):
        n = int(8 * BAR * SR)
        chunks.append((rng.uniform(0.02, 0.5) * rng.standard_normal(n)).astype(np.float32))
    y = np.concatenate(chunks)
    assert len(detect_sections(y, SR, Grid(0.0, BPM), len(y) / SR)) <= 16


def test_section_dict_round_trip():
    s = Section(1.5, 9.0, "Verso", "manual")
    assert Section.from_dict(s.to_dict()) == s
