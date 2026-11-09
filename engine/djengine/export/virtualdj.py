"""VirtualDJ 8 database.xml: merge our tracks' BPM, key, beatgrid and cues, keeping everything else intact."""
import os
import uuid
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ..errors import UserError
from .model import ExportTrack, clean_text

PROCESS_NAMES = {"virtualdj.exe", "virtualdj8.exe", "virtualdj_pc.exe"}
_CUE_NUMS = 64
BACKUPS = 5


def _documents() -> Path:
    """The user's Documents folder (follows OneDrive redirection on Windows)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

            folder = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder), 0, None, ctypes.byref(out)) == 0:
                path = out.value
                ctypes.windll.ole32.CoTaskMemFree(out)
                return Path(path)
        except Exception:
            pass
    return Path.home() / "Documents"


def database_for(track_path: str) -> Path:
    """VirtualDJ keeps one database per drive: Documents\\VirtualDJ on the system drive, <drive>:\\VirtualDJ elsewhere."""
    drive = Path(track_path).drive.upper()
    system = os.environ.get("SystemDrive", "C:").upper()
    if not drive or drive == system:
        return _documents() / "VirtualDJ" / "database.xml"
    return Path(f"{drive}\\") / "VirtualDJ" / "database.xml"


def virtualdj_running() -> bool:
    import psutil

    for p in psutil.process_iter(["name"]):
        if (p.info.get("name") or "").lower() in PROCESS_NAMES:
            return True
    return False


def _norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(p))


def _fill(song: ET.Element, t: ExportTrack) -> None:
    song.set("FileSize", str(t.size))
    tags = song.find("Tags")
    if tags is None:
        tags = ET.SubElement(song, "Tags")
    tags.set("Author", clean_text(t.artist))
    tags.set("Title", clean_text(t.title))
    tags.set("Album", clean_text(t.album))
    infos = song.find("Infos")
    if infos is None:
        infos = ET.SubElement(song, "Infos")
    infos.set("SongLength", f"{t.duration:.3f}")
    scan = song.find("Scan")
    if scan is None:
        scan = ET.SubElement(song, "Scan")
    scan.set("Version", scan.get("Version", "801"))
    scan.set("Bpm", f"{60.0 / t.bpm:.6f}")  # VirtualDJ stores seconds per beat
    if t.key:
        scan.set("Key", t.key)
    from ..prep.sections import LABELS

    # ours (the grid and cues named after a section) are replaced; cues the user made in VirtualDJ stay
    for poi in [p for p in song.findall("Poi")
                if p.get("Type") == "beatgrid" or (p.get("Type") == "cue" and p.get("Name") in LABELS)]:
        song.remove(poi)
    taken = {p.get("Num") for p in song.findall("Poi") if p.get("Type") == "cue"}
    ET.SubElement(song, "Poi", Pos=f"{t.anchor:.3f}", Type="beatgrid")
    free = (str(n) for n in range(1, _CUE_NUMS + 1) if str(n) not in taken)
    for c, num in zip(t.cues, free):
        ET.SubElement(song, "Poi", Name=c.name, Pos=f"{c.start:.3f}", Num=num, Type="cue")


def merge_database(xml_text: str | bytes | None, tracks: list[ExportTrack]) -> str:
    if xml_text:
        try:  # bytes: the parser follows the file's own encoding declaration (older databases are not UTF-8)
            root = ET.fromstring(xml_text if isinstance(xml_text, bytes) else xml_text.encode("utf-8"))
        except ET.ParseError:
            raise UserError("bad_request", "No se pudo leer la base de datos de VirtualDJ")
    else:
        root = ET.Element("VirtualDJ_Database", Version="8.5")
    by_path = {_norm(s.get("FilePath", "")): s for s in root.findall("Song")}
    for t in tracks:
        song = by_path.get(_norm(t.path))
        if song is None:
            song = ET.SubElement(root, "Song", FilePath=t.path)
            by_path[_norm(t.path)] = song
        _fill(song, t)
    ET.indent(root, space=" ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def write_virtualdj(tracks: list[ExportTrack]) -> tuple[list[Path], list[dict]]:
    """Merge into each drive's database (backup first, atomic write). Refuses while VirtualDJ is running."""
    if virtualdj_running():
        raise UserError("busy", "Cierra VirtualDJ para exportar")
    groups: dict[Path, list[ExportTrack]] = defaultdict(list)
    for t in tracks:
        groups[database_for(t.path)].append(t)
    written, skipped, plan = [], [], []
    # read and merge every drive's database first: one unreadable file means nothing is written anywhere
    for db, items in groups.items():
        if not db.parent.is_dir():
            skipped += [{"title": t.title, "reason": "No se encontró la carpeta de VirtualDJ"} for t in items]
            continue
        old = db.read_bytes() if db.exists() else None
        plan.append((db, old, merge_database(old, items)))
    for db, old, new in plan:
        if old is not None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            (db.parent / f"database.xml.bak-{stamp}").write_bytes(old)
            for stale in sorted(db.parent.glob("database.xml.bak-*"))[:-BACKUPS]:  # keep the newest few
                stale.unlink(missing_ok=True)
        tmp = db.with_name(f"~oneforall-{uuid.uuid4().hex}.part")
        try:
            tmp.write_text(new, encoding="utf-8")
            os.replace(tmp, db)
        finally:
            tmp.unlink(missing_ok=True)
        written.append(db)
    return written, skipped
