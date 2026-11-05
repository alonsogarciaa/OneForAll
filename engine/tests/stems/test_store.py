import os
from pathlib import Path

from djengine.settings import Settings
from djengine.stems.names import KARAOKE, STEMS, ext_for, stems_folder
from djengine.stems.store import StemsStore


def test_settings_defaults():
    s = Settings()
    assert (s.stems_dir, s.stems_format, s.stems_backend) == (None, "wav16", "auto")


def test_names():
    assert STEMS == ("vocals", "drums", "bass", "guitar", "piano", "other")
    assert KARAOKE == ("lead_vocals", "backing_vocals")
    assert [ext_for(f) for f in ("wav16", "wav24", "flac", "mp3")] == ["wav", "wav", "flac", "mp3"]


def test_folder_defaults_under_music_and_is_sanitized(tmp_path):
    s = Settings(music_dir=str(tmp_path))
    assert stems_folder(s, {"artist": "Quevedo", "title": "LA GRACIOSA"}) == tmp_path / "Stems" / "Quevedo - LA GRACIOSA"
    odd = stems_folder(s, {"artist": "AC/DC", "title": "Live: Now?"})
    assert not any(c in odd.name for c in '/:?')
    s2 = Settings(music_dir=str(tmp_path), stems_dir=str(tmp_path / "S"))
    assert stems_folder(s2, {"artist": "A", "title": "B"}).parent == tmp_path / "S"


def make(tmp_path, name, data=b"x"):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_store_roundtrip_and_staleness(tmp_path):
    st = StemsStore(tmp_path / "db.sqlite")
    src = make(tmp_path, "song.mp3")
    v = make(tmp_path, "vocals.wav")
    d = make(tmp_path, "drums.wav")
    st.add(src, "vocals", v, "htdemucs_6s")
    st.add(src, "drums", d, "htdemucs_6s")
    assert st.get(src) == {"vocals": v, "drums": d}
    assert st.is_stem_file(v) and not st.is_stem_file(src)
    assert st.folder_for(src) == tmp_path
    d.unlink()
    assert st.get(src) == {"vocals": v}
    stt = src.stat()
    os.utime(src, (stt.st_atime, stt.st_mtime + 10))
    assert st.get(src) == {}
    assert not st.is_stem_file(v)
