import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from djengine.errors import UserError
from djengine.export import virtualdj as vdj
from djengine.export.model import Cue, ExportTrack


def track(path=r"C:\Music\Señor & \"Co\".mp3", title='Señor & "Co"'):
    return ExportTrack(1, path, title, "Art", "Alb", 200.5, 1000, 128.0, "Am", 0.25,
                       [Cue(0.25, "Intro", (142, 142, 147), 0), Cue(30.25, "Estribillo/Drop", (255, 69, 58), 1)], "MP3 File")


def songs(xml):
    return ET.fromstring(xml.encode("utf-8")).findall("Song")


def test_merge_into_empty():
    root = ET.fromstring(vdj.merge_database(None, [track()]).encode("utf-8"))
    assert root.tag == "VirtualDJ_Database"
    s = root.find("Song")
    assert s.get("FilePath") == r"C:\Music\Señor & \"Co\".mp3" and s.get("FileSize") == "1000"
    scan = s.find("Scan")
    assert scan.get("Bpm") == "0.468750" and scan.get("Key") == "Am" and scan.get("Version") == "801"
    pois = s.findall("Poi")
    assert pois[0].attrib == {"Pos": "0.250", "Type": "beatgrid"}
    assert [(p.get("Name"), p.get("Num"), p.get("Type")) for p in pois[1:]] == [("Intro", "1", "cue"), ("Estribillo/Drop", "2", "cue")]
    assert s.find("Tags").get("Title") == 'Señor & "Co"' and s.find("Infos").get("SongLength") == "200.500"


def test_merge_keeps_foreign_songs_and_attributes():
    existing = ('<?xml version="1.0" encoding="UTF-8"?>\n<VirtualDJ_Database Version="8.5">\n'
                ' <Song FilePath="D:/other.mp3" FileSize="9"><Tags Author="X" Title="Y" /></Song>\n'
                f' <Song FilePath="{track().path.replace("&", "&amp;").replace(chr(34), "&quot;")}" FileSize="5">'
                '<Tags Author="Old" Title="Old" Stars="5" /><Scan Version="801" Bpm="0.5" Volume="1.2" />'
                '<Poi Pos="9" Type="beatgrid" /><Poi Name="Mine" Pos="3" Num="1" Type="cue" /><Comment>hi</Comment></Song>\n'
                '</VirtualDJ_Database>\n')
    out = vdj.merge_database(existing, [track()])
    root = ET.fromstring(out.encode("utf-8"))
    assert root.get("Version") == "8.5"
    ss = root.findall("Song")
    assert len(ss) == 2 and ss[0].get("FilePath") == "D:/other.mp3" and ss[0].find("Tags").get("Title") == "Y"
    ours = ss[1]
    assert ours.find("Tags").get("Stars") == "5" and ours.find("Tags").get("Title") == 'Señor & "Co"'
    assert ours.find("Scan").get("Volume") == "1.2" and ours.find("Scan").get("Bpm") == "0.468750"
    assert ours.find("Comment").text == "hi"
    assert len([p for p in ours.findall("Poi") if p.get("Type") == "beatgrid"]) == 1
    assert [p.get("Name") for p in ours.findall("Poi") if p.get("Type") == "cue"] == ["Intro", "Estribillo/Drop"]


def test_merge_twice_no_duplicates():
    once = vdj.merge_database(None, [track()])
    twice = vdj.merge_database(once, [track()])
    assert len(songs(twice)) == 1 and len(songs(twice)[0].findall("Poi")) == 3


def test_unreadable_db_aborts():
    with pytest.raises(UserError) as e:
        vdj.merge_database("<VirtualDJ_Database><Song", [track()])
    assert e.value.message == "No se pudo leer la base de datos de VirtualDJ"


def test_running_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(vdj, "virtualdj_running", lambda: True)
    with pytest.raises(UserError) as e:
        vdj.write_virtualdj([track()])
    assert e.value.message == "Cierra VirtualDJ para exportar"


def test_backup_and_atomic_write(tmp_path, monkeypatch):
    monkeypatch.setattr(vdj, "virtualdj_running", lambda: False)
    db = tmp_path / "VirtualDJ" / "database.xml"
    db.parent.mkdir()
    db.write_text('<VirtualDJ_Database Version="8.5" />', encoding="utf-8")
    monkeypatch.setattr(vdj, "database_for", lambda p: db)
    written, skipped = vdj.write_virtualdj([track()])
    assert written == [db] and skipped == []
    assert len(songs(db.read_text(encoding="utf-8"))) == 1
    backups = [p.name for p in db.parent.iterdir() if p.name.startswith("database.xml.bak-")]
    assert len(backups) == 1 and not [p for p in db.parent.iterdir() if p.suffix == ".part"]


def test_missing_virtualdj_folder_skips(tmp_path, monkeypatch):
    monkeypatch.setattr(vdj, "virtualdj_running", lambda: False)
    monkeypatch.setattr(vdj, "database_for", lambda p: tmp_path / "nope" / "database.xml")
    written, skipped = vdj.write_virtualdj([track()])
    assert written == [] and skipped == [{"title": 'Señor & "Co"', "reason": "No se encontró la carpeta de VirtualDJ"}]


@pytest.mark.skipif(os.name != "nt", reason="Windows drives")
def test_database_for_other_drive(monkeypatch):
    monkeypatch.setenv("SystemDrive", "C:")
    assert vdj.database_for(r"D:\Music\x.mp3") == Path(r"D:\VirtualDJ\database.xml")
    assert vdj.database_for(r"C:\Music\x.mp3").name == "database.xml"
    assert vdj.database_for(r"C:\Music\x.mp3").parent.name == "VirtualDJ"
