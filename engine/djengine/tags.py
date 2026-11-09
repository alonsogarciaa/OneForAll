import base64
import io
from dataclasses import dataclass
from pathlib import Path

import mutagen
from mutagen.aiff import AIFF
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, COMM, ID3, TALB, TBPM, TDRC, TIT2, TKEY, TPE1
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE
from PIL import Image

MP4_KEY = "----:com.apple.iTunes:initialkey"


@dataclass
class TrackMeta:
    title: str
    artist: str
    album: str = ""
    year: str = ""
    source_url: str = ""
    bpm: float | None = None
    key: str | None = None


def square_cover(img: bytes, size: int = 600) -> bytes:
    im = Image.open(io.BytesIO(img)).convert("RGB")
    side = min(im.size)
    left = (im.width - side) // 2
    top = (im.height - side) // 2
    im = im.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90)
    return out.getvalue()


def _mime(data: bytes) -> str:
    return "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def _bpm_text(bpm: float) -> str:
    return f"{round(bpm, 2):g}"


# --- ID3 (mp3, wav, aiff) ------------------------------------------------------
def _write_id3(audio, meta: TrackMeta, cover: bytes | None) -> None:
    if audio.tags is None:
        audio.add_tags()
    t: ID3 = audio.tags
    for frame in ("TIT2", "TPE1", "TALB", "TDRC", "COMM", "APIC", "TBPM", "TKEY"):
        t.delall(frame)
    t.add(TIT2(encoding=3, text=meta.title))
    t.add(TPE1(encoding=3, text=meta.artist))
    if meta.album:
        t.add(TALB(encoding=3, text=meta.album))
    if meta.year:
        t.add(TDRC(encoding=3, text=meta.year))
    if meta.source_url:
        t.add(COMM(encoding=3, lang="eng", desc="", text=meta.source_url))
    if cover:
        t.add(APIC(encoding=3, mime=_mime(cover), type=3, desc="Cover", data=cover))
    if meta.bpm is not None:
        t.add(TBPM(encoding=3, text=_bpm_text(meta.bpm)))
    if meta.key:
        t.add(TKEY(encoding=3, text=meta.key))
    if isinstance(audio, MP3):
        audio.save(v2_version=4)
    else:
        audio.save()


def _read_id3(audio) -> TrackMeta:
    t = audio.tags or {}

    def txt(frame: str) -> str:
        f = t.get(frame)
        return str(f.text[0]) if f and f.text else ""

    comm = next((f for k, f in t.items() if k.startswith("COMM")), None)
    bpm = txt("TBPM")
    return TrackMeta(
        title=txt("TIT2"), artist=txt("TPE1"), album=txt("TALB"), year=txt("TDRC"),
        source_url=str(comm.text[0]) if comm and comm.text else "",
        bpm=float(bpm) if bpm else None, key=txt("TKEY") or None,
    )


# --- MP4 (aac, alac) ---------------------------------------------------------------
def _write_mp4(audio: MP4, meta: TrackMeta, cover: bytes | None) -> None:
    if audio.tags is None:
        audio.add_tags()
    t = audio.tags
    for k in ("©nam", "©ART", "©alb", "©day", "©cmt", "covr", "tmpo", MP4_KEY):
        t.pop(k, None)
    t["©nam"] = [meta.title]
    t["©ART"] = [meta.artist]
    if meta.album:
        t["©alb"] = [meta.album]
    if meta.year:
        t["©day"] = [meta.year]
    if meta.source_url:
        t["©cmt"] = [meta.source_url]
    if cover:
        fmt = MP4Cover.FORMAT_PNG if _mime(cover) == "image/png" else MP4Cover.FORMAT_JPEG
        t["covr"] = [MP4Cover(cover, imageformat=fmt)]
    if meta.bpm is not None:
        t["tmpo"] = [int(round(meta.bpm))]  # the atom only holds integers
    if meta.key:
        t[MP4_KEY] = [MP4FreeForm(meta.key.encode("utf-8"))]
    audio.save()


def _read_mp4(audio: MP4) -> TrackMeta:
    t = audio.tags or {}

    def first(k: str) -> str:
        v = t.get(k)
        return str(v[0]) if v else ""

    key = t.get(MP4_KEY)
    tmpo = t.get("tmpo")
    return TrackMeta(
        title=first("©nam"), artist=first("©ART"), album=first("©alb"), year=first("©day"),
        source_url=first("©cmt"), bpm=float(tmpo[0]) if tmpo else None,
        key=bytes(key[0]).decode("utf-8") if key else None,
    )


# --- Vorbis comments (flac, ogg, opus) ---------------------------------------------
def _picture(cover: bytes) -> Picture:
    pic = Picture()
    pic.type = 3
    pic.mime = _mime(cover)
    pic.desc = "Cover"
    pic.data = cover
    im = Image.open(io.BytesIO(cover))
    pic.width, pic.height = im.size
    pic.depth = 24
    return pic


def _write_vorbis(audio, meta: TrackMeta, cover: bytes | None) -> None:
    if audio.tags is None:
        audio.add_tags()
    t = audio.tags
    for k in ("TITLE", "ARTIST", "ALBUM", "DATE", "COMMENT", "BPM", "INITIALKEY", "METADATA_BLOCK_PICTURE"):
        if k in t:
            del t[k]
    t["TITLE"] = meta.title
    t["ARTIST"] = meta.artist
    if meta.album:
        t["ALBUM"] = meta.album
    if meta.year:
        t["DATE"] = meta.year
    if meta.source_url:
        t["COMMENT"] = meta.source_url
    if meta.bpm is not None:
        t["BPM"] = _bpm_text(meta.bpm)
    if meta.key:
        t["INITIALKEY"] = meta.key
    if isinstance(audio, FLAC):
        audio.clear_pictures()
        if cover:
            audio.add_picture(_picture(cover))
    elif cover:
        t["METADATA_BLOCK_PICTURE"] = base64.b64encode(_picture(cover).write()).decode("ascii")
    audio.save()


def _read_vorbis(audio) -> TrackMeta:
    t = audio.tags or {}

    def first(k: str) -> str:
        v = t.get(k)
        return v[0] if v else ""

    bpm = first("BPM")
    return TrackMeta(
        title=first("TITLE"), artist=first("ARTIST"), album=first("ALBUM"), year=first("DATE"),
        source_url=first("COMMENT"), bpm=float(bpm) if bpm else None, key=first("INITIALKEY") or None,
    )


# --- public ------------------------------------------------------------------------
def _open(path: Path):
    audio = mutagen.File(path)
    if audio is None:
        raise ValueError(f"formato de audio no reconocido: {path}")
    return audio


def write_tags(path: Path, meta: TrackMeta, cover: bytes | None) -> None:
    audio = _open(Path(path))
    if isinstance(audio, (MP3, WAVE, AIFF)):
        _write_id3(audio, meta, cover)
    elif isinstance(audio, MP4):
        _write_mp4(audio, meta, cover)
    elif isinstance(audio, (FLAC, OggVorbis, OggOpus)):
        _write_vorbis(audio, meta, cover)
    else:
        raise ValueError(f"etiquetas no soportadas para {type(audio).__name__}")


def read_tags(path: Path) -> TrackMeta:
    audio = _open(Path(path))
    if isinstance(audio, (MP3, WAVE, AIFF)):
        return _read_id3(audio)
    if isinstance(audio, MP4):
        return _read_mp4(audio)
    return _read_vorbis(audio)


def read_cover(path: Path) -> bytes | None:
    """The embedded front cover, if any (ID3 APIC, MP4 covr or FLAC/Vorbis picture)."""
    audio = _open(Path(path))
    tags = audio.tags
    if tags is None:
        return None
    if isinstance(audio, (MP3, WAVE, AIFF)):
        pics = tags.getall("APIC")
        return bytes(pics[0].data) if pics else None
    if isinstance(audio, MP4):
        covr = tags.get("covr")
        return bytes(covr[0]) if covr else None
    pics = getattr(audio, "pictures", None)
    return bytes(pics[0].data) if pics else None


def set_bpm_key(path: Path, bpm: float | None, key: str | None) -> None:
    """Edit only the BPM and key fields in place; every other tag, comment and picture is left alone.

    A None value leaves that field as it is (silence or failed estimate never erases user data).
    """
    audio = _open(Path(path))
    if audio.tags is None:
        audio.add_tags()
    t = audio.tags
    bpm_txt = _bpm_text(round(bpm)) if bpm else None
    if isinstance(audio, (MP3, WAVE, AIFF)):
        if bpm_txt:
            t.setall("TBPM", [TBPM(encoding=3, text=bpm_txt)])
        if key:
            t.setall("TKEY", [TKEY(encoding=3, text=key)])
    elif isinstance(audio, MP4):
        if bpm:
            t["tmpo"] = [int(round(bpm))]
        if key:
            t[MP4_KEY] = [MP4FreeForm(key.encode("utf-8"))]
    elif isinstance(audio, (FLAC, OggVorbis, OggOpus)):
        if bpm_txt:
            t["BPM"] = bpm_txt
        if key:
            t["INITIALKEY"] = key
    else:
        raise ValueError(f"etiquetas no soportadas para {type(audio).__name__}")
    audio.save()
