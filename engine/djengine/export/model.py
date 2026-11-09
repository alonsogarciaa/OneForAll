"""What every DJ-software exporter needs about a track, collected from the library and the analysis."""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..prep.sections import COLORS, Section

KINDS = {".mp3": "MP3 File", ".wav": "WAV File", ".flac": "FLAC File", ".m4a": "M4A File", ".aiff": "AIFF File",
         ".aif": "AIFF File", ".ogg": "OGG File", ".opus": "OPUS File"}
HOT_CUES = 8


@dataclass
class Cue:
    start: float
    name: str
    color: tuple[int, int, int]
    hot: int | None


@dataclass
class ExportTrack:
    id: int
    path: str
    title: str
    artist: str
    album: str
    duration: float
    size: int
    bpm: float
    key: str
    anchor: float
    cues: list[Cue] = field(default_factory=list)
    kind: str = ""


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_text(s: str) -> str:
    """Drop control characters: XML 1.0 cannot hold them, and DJ programs refuse such files."""
    return _CONTROL.sub("", s or "")


def english_key(tonic: str | None, mode: str | None) -> str:
    if not tonic or not mode:
        return ""
    return tonic + ("m" if mode == "minor" else "")


def cues_for(sections: list[Section]) -> list[Cue]:
    """One memory cue per section; the first 8 are also hot cues A-H."""
    return [Cue(round(s.start, 3), s.label, COLORS.get(s.label, (255, 255, 255)), i if i < HOT_CUES else None)
            for i, s in enumerate(sections)]


def collect(svc, track_ids: list[int] | None) -> tuple[list[ExportTrack], list[dict]]:
    wanted = None if track_ids is None else set(track_ids)
    tracks, skipped = [], []
    for t in svc.library.list_tracks():
        if wanted is not None and t.id not in wanted:
            continue
        p = Path(t.path)
        if not p.is_file():
            skipped.append({"title": t.title, "reason": "Archivo no encontrado"})
            continue
        rec = svc.analysis.get(p)
        if rec is None or not rec.bpm:
            skipped.append({"title": t.title, "reason": "Sin analizar"})
            continue
        side = svc.analysis.read_sidecar(p) or {}
        grid = svc.analysis.get_grid(p)
        tracks.append(ExportTrack(
            id=t.id, path=str(p), title=t.title, artist=t.artist, album=t.album or "",
            duration=float(side.get("duration") or t.duration_s or 0), size=os.path.getsize(p),
            bpm=float(grid.bpm if grid and grid.bpm else rec.bpm), key=english_key(rec.tonic, rec.mode),
            anchor=float(grid.anchor if grid else 0.0), cues=cues_for(svc.analysis.get_sections(p)),
            kind=KINDS.get(p.suffix.lower(), "Audio File"),
        ))
    return tracks, skipped


def mp3_decoder_offset(path) -> float:
    """Seconds a decoder that ignores gapless info plays before our analysis' time 0 (0 without a LAME tag).

    Xing/Info header, then the LAME tag: 9-byte encoder version, ..., encoder delay in 12 bits at byte 21.
    ffmpeg writes the same tag with a "Lavc"/"Lavf" version string, so it is parsed here, not with mutagen.
    """
    p = Path(path)
    if p.suffix.lower() != ".mp3":
        return 0.0
    try:
        from mutagen.mp3 import MP3

        sr = MP3(p).info.sample_rate
        head = p.read_bytes()[: 1 << 18]
    except Exception:
        return 0.0
    start = 0
    if head[:3] == b"ID3" and len(head) >= 10:  # skip the ID3v2 tag: its text may contain "Info" or "Xing"
        start = 10 + ((head[6] & 0x7F) << 21 | (head[7] & 0x7F) << 14 | (head[8] & 0x7F) << 7 | (head[9] & 0x7F))
    frame = head[start: start + 2048]  # the Xing/Info header lives inside the first MPEG frame
    for marker in (b"Xing", b"Info"):
        rel = frame.find(marker)
        if rel < 0:
            continue
        pos = start + rel
        if pos + 8 > len(head):
            continue
        flags = int.from_bytes(head[pos + 4: pos + 8], "big")
        tag = pos + 8 + 4 * bool(flags & 1) + 4 * bool(flags & 2) + 100 * bool(flags & 4) + 4 * bool(flags & 8)
        version = head[tag: tag + 4]
        if version not in (b"LAME", b"Lavc", b"Lavf", b"GOGO") or tag + 23 > len(head):
            continue
        delay = (head[tag + 21] << 4) | (head[tag + 22] >> 4)
        return round((delay + 529) / sr, 4)
    return 0.0
