"""Does a recommendation fit the reference? "encaja": compatible key and tempo; "cerca": only one of them."""
from typing import Literal

from ..analysis.camelot import compatible

TOLERANCE = 0.06


def _bpm_ok(ref: float, bpm: float) -> bool:
    return any(abs(bpm * m - ref) / ref <= TOLERANCE for m in (1.0, 2.0, 0.5))  # half and double time mix too


def fit(ref_bpm: float | None, ref_camelot: str | None, bpm: float | None,
        camelot: str | None) -> Literal["encaja", "cerca"] | None:
    tempo = _bpm_ok(ref_bpm, bpm) if ref_bpm and bpm else None
    key = compatible(ref_camelot, camelot) is not None if ref_camelot and camelot else None
    if tempo and key:
        return "encaja"
    if tempo or key:
        return "cerca"
    return None
