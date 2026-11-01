from typing import Literal

Mode = Literal["major", "minor"]
Level = Literal["same", "adjacent", "relative"]

PITCHES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
SPANISH = ["Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si"]

# Camelot number for each pitch class: minor keys (A) and major keys (B).
_MINOR = {"G#": 1, "D#": 2, "A#": 3, "F": 4, "C": 5, "G": 6, "D": 7, "A": 8, "E": 9, "B": 10, "F#": 11, "C#": 12}
_MAJOR = {"B": 1, "F#": 2, "C#": 3, "G#": 4, "D#": 5, "A#": 6, "F": 7, "C": 8, "G": 9, "D": 10, "A": 11, "E": 12}
_FROM = {**{f"{n}A": (p, "minor") for p, n in _MINOR.items()}, **{f"{n}B": (p, "major") for p, n in _MAJOR.items()}}


def to_camelot(tonic: str, mode: Mode) -> str:
    return f"{_MINOR[tonic]}A" if mode == "minor" else f"{_MAJOR[tonic]}B"


def from_camelot(code: str) -> tuple[str, str]:
    return _FROM[code.upper()]


def display_key(tonic: str, mode: Mode) -> str:
    name = SPANISH[PITCHES.index(tonic)] + ("m" if mode == "minor" else "")
    return f"{to_camelot(tonic, mode)} · {name}"


def tag_key(tonic: str, mode: Mode, notation: str) -> str:
    if notation == "musical":
        return tonic + ("m" if mode == "minor" else "")
    return to_camelot(tonic, mode)


def _split(code: str) -> tuple[int, str]:
    return int(code[:-1]), code[-1].upper()


def compatible(a: str, b: str) -> Level | None:
    na, la = _split(a)
    nb, lb = _split(b)
    if (na, la) == (nb, lb):
        return "same"
    if la == lb and (na - nb) % 12 in (1, 11):
        return "adjacent"
    if na == nb:
        return "relative"
    return None
