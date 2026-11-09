"""rekordbox.xml (DJ_PLAYLISTS 1.0.0): tracks with BPM, key, a fixed TEMPO grid and memory/hot cues."""
import os
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

from .model import ExportTrack, mp3_decoder_offset, clean_text


def _location(path: str) -> str:
    return "file://localhost/" + quote(path.replace("\\", "/"), safe="/:")


def rekordbox_xml(tracks: list[ExportTrack], playlists: list[tuple[str, list[int]]]) -> str:
    root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
    ET.SubElement(root, "PRODUCT", Name="OneForAll", Version="0.1.0", Company="OneForAll")
    coll = ET.SubElement(root, "COLLECTION", Entries=str(len(tracks)))
    for t in tracks:
        off = mp3_decoder_offset(t.path)  # Rekordbox counts from the first decoded sample, gapless delay included
        el = ET.SubElement(coll, "TRACK", TrackID=str(t.id), Name=clean_text(t.title), Artist=clean_text(t.artist),
                           Album=clean_text(t.album),
                           Kind=t.kind, Size=str(t.size), TotalTime=str(int(t.duration)),
                           AverageBpm=f"{t.bpm:.2f}", Tonality=t.key, Location=_location(t.path))
        ET.SubElement(el, "TEMPO", Inizio=f"{t.anchor + off:.3f}", Bpm=f"{t.bpm:.2f}", Metro="4/4", Battito="1")
        for c in t.cues:
            start = f"{c.start + off:.3f}"
            ET.SubElement(el, "POSITION_MARK", Name=c.name, Type="0", Start=start, Num="-1")
            if c.hot is not None:
                r, g, b = c.color
                ET.SubElement(el, "POSITION_MARK", Name=c.name, Type="0", Start=start, Num=str(c.hot),
                              Red=str(r), Green=str(g), Blue=str(b))
    ids = {t.id for t in tracks}
    lists = [(name, [i for i in members if i in ids]) for name, members in playlists]
    pls = ET.SubElement(root, "PLAYLISTS")
    top = ET.SubElement(pls, "NODE", Type="0", Name="ROOT", Count="1")
    folder = ET.SubElement(top, "NODE", Type="0", Name="OneForAll", Count=str(len(lists)))
    for name, members in lists:
        node = ET.SubElement(folder, "NODE", Name=clean_text(name), Type="1", KeyType="0", Entries=str(len(members)))
        for i in members:
            ET.SubElement(node, "TRACK", Key=str(i))
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def write_rekordbox(path_out: Path, xml: str) -> None:
    path_out = Path(path_out)
    path_out.parent.mkdir(parents=True, exist_ok=True)
    tmp = path_out.with_name(f"~oneforall-{uuid.uuid4().hex}.part")
    try:
        tmp.write_text(xml, encoding="utf-8")
        os.replace(tmp, path_out)
    finally:
        tmp.unlink(missing_ok=True)
