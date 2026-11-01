"""Standard tempo and key evaluation measures (MIREX)."""
from djengine.analysis.camelot import from_camelot, to_camelot

_FLAT = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#", "Cb": "B", "Fb": "E", "E#": "F", "B#": "C"}


def accuracy1(pred: float, ref: float, tol: float = 0.04) -> bool:
    return abs(pred - ref) <= tol * ref


def accuracy2(pred: float, ref: float, tol: float = 0.04) -> bool:
    return any(accuracy1(pred, ref * f, tol) for f in (1, 2, 0.5, 3, 1 / 3))


def mirex_score(pred: str, ref: str) -> float:
    """1 exact, 0.5 perfect fifth (±1 on the wheel, same mode), 0.3 relative, 0.2 parallel, else 0."""
    if pred == ref:
        return 1.0
    pn, pl = int(pred[:-1]), pred[-1]
    rn, rl = int(ref[:-1]), ref[-1]
    if pl == rl and (pn - rn) % 12 in (1, 11):
        return 0.5
    if pn == rn:
        return 0.3
    if from_camelot(pred)[0] == from_camelot(ref)[0]:
        return 0.2
    return 0.0


def parse_key_label(label: str) -> str | None:
    """'C minor' / 'Eb major' (GiantSteps annotations) -> Camelot code."""
    parts = label.strip().split()[:2]  # "Bb minor dorian": modal hint ignored
    if len(parts) != 2 or parts[1].lower() not in ("major", "minor"):
        return None
    tonic = _FLAT.get(parts[0], parts[0])
    try:
        return to_camelot(tonic, parts[1].lower())
    except KeyError:
        return None
