"""Defaults chosen by the GiantSteps benchmark (docs/bench/2026-11-fase2.md)."""

# Tempo: deeprhythm, Accuracy2 95.8 % vs Beatport BPM (N=527), 97.7 % vs expert subset (N=43)
DEFAULT_TEMPO_METHOD = "deeprhythm"
# Key: madmom CNN, MIREX 0.797 / exact 73.0 % (N=566); best template (edma) 0.637
DEFAULT_KEY_METHOD = "cnn"
ANALYSIS_VERSION = 2  # 2: fixed grid and sections
