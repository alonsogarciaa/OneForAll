"""Analysis may only touch BPM and key: every other tag, comment and picture must survive."""
import asyncio
import io

import mutagen
import pytest
from mutagen.id3 import COMM, TPE1
from PIL import Image

from djengine.convert import FORMATS, ConvertOptions, convert_file
from djengine.tags import TrackMeta, read_tags, set_bpm_key, write_tags
from tests.conftest import FakeCtx


def png() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (32, 32), (0, 128, 255)).save(b, "PNG")
    return b.getvalue()


@pytest.fixture
def make(sine_wav, tmp_path):
    def _make(fmt):
        dst = tmp_path / f"t.{FORMATS[fmt].ext}"
        asyncio.run(convert_file(FakeCtx(tmp_path / f"j{fmt}"), sine_wav, dst, ConvertOptions(format=fmt), 3.0))
        write_tags(dst, TrackMeta("Título", "Artista", "Álbum", "2024", "https://youtu.be/x"), png())
        return dst

    return _make


def has_cover(p) -> bool:
    f = mutagen.File(p)
    t = f.tags
    if hasattr(f, "pictures") and f.pictures:
        return True
    return any(str(k).startswith("APIC") for k in t.keys()) or "covr" in t or "METADATA_BLOCK_PICTURE" in t


@pytest.mark.parametrize("fmt", ["mp3", "aac", "flac", "ogg", "opus", "wav", "aiff"])
def test_only_bpm_and_key_change(make, fmt):
    p = make(fmt)
    set_bpm_key(p, 128, "8A")
    m = read_tags(p)
    assert (m.title, m.artist, m.album, m.year, m.source_url) == ("Título", "Artista", "Álbum", "2024", "https://youtu.be/x")
    assert m.bpm == 128.0 and m.key == "8A"
    assert has_cover(p), f"{fmt} lost its cover"


def test_mp3_keeps_foreign_frames(make):
    p = make("mp3")
    f = mutagen.File(p)
    f.tags.add(COMM(encoding=3, lang="eng", desc="iTunNORM", text="00000A"))
    f.tags.setall("TPE1", [TPE1(encoding=3, text=["Uno", "Dos"])])
    f.save()
    set_bpm_key(p, 100, "5A")
    t = mutagen.File(p).tags
    assert str(t["COMM:iTunNORM:eng"].text[0]) == "00000A"
    assert list(t["TPE1"].text) == ["Uno", "Dos"]


def test_missing_bpm_leaves_existing_value(make):
    p = make("mp3")
    set_bpm_key(p, 124, "8A")
    set_bpm_key(p, None, None)
    m = read_tags(p)
    assert m.bpm == 124.0 and m.key == "8A"
