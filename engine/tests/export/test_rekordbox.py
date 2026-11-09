import os
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

import pytest

from djengine.export.model import Cue, ExportTrack
from djengine.export.rekordbox import rekordbox_xml, write_rekordbox

GOLDEN = Path(__file__).parent / "golden_rekordbox.xml"


def tracks():
    a = ExportTrack(1, r"C:\Música\Canción & Co #1 100%.mp3", "Canción & Co", "Bad Bunny", "Un Verano", 213.4, 8_000_000,
                    92.0, "Am", 0.512, [Cue(0.512, "Intro", (142, 142, 147), 0), Cue(21.38, "Estribillo/Drop", (255, 69, 58), 1)],
                    "MP3 File")
    b = ExportTrack(2, r"D:\DJ\x.wav", 'Say "Hi"', "<Artist>", "", 180.0, 31_000_000, 128.0, "F#", 0.0, [], "WAV File")
    return [a, b]


def test_rekordbox_golden():
    out = rekordbox_xml(tracks(), [("Perreo", [1, 2])])
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(out, encoding="utf-8")
    assert out == GOLDEN.read_text(encoding="utf-8")


def test_location_round_trip():
    root = ET.fromstring(rekordbox_xml(tracks(), []).encode("utf-8"))
    loc = root.find("COLLECTION/TRACK").get("Location")
    assert loc.startswith("file://localhost/")
    assert unquote(loc[len("file://localhost/"):]) == r"C:\Música\Canción & Co #1 100%.mp3".replace("\\", "/")


def test_rekordbox_parses():
    root = ET.fromstring(rekordbox_xml(tracks(), [("Perreo", [1, 2])]).encode("utf-8"))
    assert root.tag == "DJ_PLAYLISTS" and root.find("COLLECTION").get("Entries") == "2"
    t = root.find("COLLECTION/TRACK")
    assert (t.get("AverageBpm"), t.get("Tonality"), t.get("TotalTime"), t.get("Kind")) == ("92.00", "Am", "213", "MP3 File")
    tempo = t.find("TEMPO")
    assert (tempo.get("Inizio"), tempo.get("Bpm"), tempo.get("Metro"), tempo.get("Battito")) == ("0.512", "92.00", "4/4", "1")
    marks = t.findall("POSITION_MARK")
    assert [(m.get("Name"), m.get("Num")) for m in marks] == [("Intro", "-1"), ("Intro", "0"), ("Estribillo/Drop", "-1"), ("Estribillo/Drop", "1")]
    hot = marks[3]
    assert (hot.get("Red"), hot.get("Green"), hot.get("Blue"), hot.get("Start")) == ("255", "69", "58", "21.380")
    pl = root.find("PLAYLISTS/NODE/NODE/NODE")
    assert pl.get("Name") == "Perreo" and [k.get("Key") for k in pl.findall("TRACK")] == ["1", "2"]


def test_write_atomic_overwrite(tmp_path):
    out = tmp_path / "rb.xml"
    write_rekordbox(out, "<a/>")
    write_rekordbox(out, "<b/>")
    assert out.read_text(encoding="utf-8") == "<b/>" and [p.name for p in tmp_path.iterdir()] == ["rb.xml"]
