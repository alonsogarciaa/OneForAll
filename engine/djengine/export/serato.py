"""Serato's own tags inside each file: BPM (Autotags), a fixed BeatGrid and hot cues (Markers2).

Byte layouts from the community documentation (github.com/Holzhaus/serato-tags, MIT). Only these three
tags are written; the audio and every other tag stay as they were.
"""
import base64
import struct
from pathlib import Path

from ..errors import UserError
from .model import Cue, ExportTrack

MIME = b"application/octet-stream\x00\x00"
NAMES = {"autotags": "Serato Autotags", "beatgrid": "Serato BeatGrid", "markers2": "Serato Markers2"}
FLAC_KEYS = {"autotags": "SERATO_AUTOTAGS", "beatgrid": "SERATO_BEATGRID", "markers2": "SERATO_MARKERS_V2"}
MP4_KEYS = {"autotags": "----:com.serato.dj:autotags", "beatgrid": "----:com.serato.dj:beatgrid",
            "markers2": "----:com.serato.dj:markersv2"}
MARKERS2_MIN = 470


def encode_autotags(bpm: float) -> bytes:
    return b"\x01\x01" + f"{bpm:.2f}".encode() + b"\x00" + b"0.000\x00" + b"0.000\x00"


def encode_beatgrid(anchor: float, bpm: float) -> bytes:
    # one terminal marker: position + BPM, then a footer byte
    return b"\x01\x00" + struct.pack(">I", 1) + struct.pack(">f", anchor) + struct.pack(">f", bpm) + b"\x00"


def decode_beatgrid(b: bytes) -> tuple[float, float]:
    (count,) = struct.unpack(">I", b[2:6])
    off = 6 + (count - 1) * 8
    pos, bpm = struct.unpack(">ff", b[off:off + 8])
    return round(pos, 4), round(bpm, 4)


def _entry(name: bytes, data: bytes) -> bytes:
    return name + b"\x00" + struct.pack(">I", len(data)) + data


def encode_markers2(cues: list[Cue]) -> bytes:
    payload = b"\x01\x01" + _entry(b"COLOR", b"\x00\xff\xff\xff")
    for c in cues:
        if c.hot is None:
            continue  # Serato has no memory cues: only hot cues A-H
        r, g, bl = c.color
        data = (b"\x00" + bytes([c.hot]) + struct.pack(">I", int(round(c.start * 1000))) + b"\x00"
                + bytes([r, g, bl]) + b"\x00\x00" + c.name.encode("utf-8") + b"\x00")
        payload += _entry(b"CUE", data)
    payload += _entry(b"BPMLOCK", b"\x00") + b"\x00"
    text = base64.b64encode(payload).rstrip(b"=")
    lines = b"\n".join(text[i:i + 72] for i in range(0, len(text), 72))
    content = b"\x01\x01" + lines
    return content + b"\x00" * max(0, MARKERS2_MIN - len(content))


def decode_markers2(content: bytes) -> list[Cue]:
    text = content[2:].split(b"\x00", 1)[0].replace(b"\n", b"")
    payload = base64.b64decode(text + b"=" * (-len(text) % 4))
    i, cues = 2, []
    while i < len(payload):
        end = payload.find(b"\x00", i)
        if end <= i:
            break
        name = payload[i:end]
        (n,) = struct.unpack(">I", payload[end + 1:end + 5])
        data = payload[end + 5:end + 5 + n]
        i = end + 5 + n
        if name == b"CUE":
            hot = data[1]
            (ms,) = struct.unpack(">I", data[2:6])
            color = (data[7], data[8], data[9])
            label = data[12:].split(b"\x00", 1)[0].decode("utf-8")
            cues.append(Cue(ms / 1000, label, color, hot))
    return cues


def _wrapped(kind: str, content: bytes) -> str:
    """FLAC/M4A store the GEOB-like body base64-encoded, behind a MIME and name header."""
    return base64.b64encode(MIME + NAMES[kind].encode() + b"\x00" + content).decode("ascii")


def _unwrapped(text: str | bytes) -> bytes:
    raw = base64.b64decode(text + ("=" * (-len(text) % 4) if isinstance(text, str) else b"=" * (-len(text) % 4)))
    return raw.split(b"\x00", 3)[3]  # mime \0 \0 name \0 content


def _contents(track: ExportTrack) -> dict[str, bytes]:
    return {"autotags": encode_autotags(track.bpm), "beatgrid": encode_beatgrid(track.anchor, track.bpm),
            "markers2": encode_markers2(track.cues)}


def write_serato(path, track: ExportTrack) -> None:
    p = Path(path)
    ext = p.suffix.lower()
    contents = _contents(track)
    try:
        if ext == ".mp3":
            from mutagen.id3 import GEOB, ID3, ID3NoHeaderError

            try:
                tags = ID3(p)
            except ID3NoHeaderError:
                tags = ID3()
            for kind, body in contents.items():
                tags.delall(f"GEOB:{NAMES[kind]}")
                tags.add(GEOB(encoding=0, mime="application/octet-stream", filename="", desc=NAMES[kind], data=body))
            tags.save(p)
        elif ext == ".flac":
            from mutagen.flac import FLAC

            audio = FLAC(p)
            for kind, body in contents.items():
                audio[FLAC_KEYS[kind]] = [_wrapped(kind, body)]
            audio.save()
        elif ext in (".m4a", ".mp4"):
            from mutagen.mp4 import MP4, MP4FreeForm

            audio = MP4(p)
            for kind, body in contents.items():
                audio[MP4_KEYS[kind]] = [MP4FreeForm(_wrapped(kind, body).encode("ascii"))]
            audio.save()
        else:
            raise UserError("unsupported", "Formato no compatible con Serato")
    except PermissionError:
        raise UserError("busy", "Archivo en uso")


def read_serato(path) -> dict:
    """What write_serato stored (for checks and tests)."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".mp3":
        from mutagen.id3 import ID3

        tags = ID3(p)
        got = {k: tags[f"GEOB:{n}"].data for k, n in NAMES.items()}
    elif ext == ".flac":
        from mutagen.flac import FLAC

        audio = FLAC(p)
        got = {k: _unwrapped(audio[FLAC_KEYS[k]][0]) for k in NAMES}
    else:
        from mutagen.mp4 import MP4

        audio = MP4(p)
        got = {k: _unwrapped(bytes(audio[MP4_KEYS[k]][0])) for k in NAMES}
    bpm = float(got["autotags"][2:].split(b"\x00", 1)[0])
    return {"bpm": bpm, "grid": decode_beatgrid(got["beatgrid"]), "cues": decode_markers2(got["markers2"])}


def export_serato(svc, track: ExportTrack) -> None:
    """Write the tags, then restamp the analysis and stems: our own tag write must not make them stale."""
    from ..analysis.store import file_stamp

    p = Path(track.path)
    before = file_stamp(p)
    write_serato(p, track)
    svc.analysis.restamp(p)
    svc.stems.restamp(p, before)
