import asyncio
import io

import pytest
from PIL import Image

from djengine.convert import FORMATS, ConvertOptions, convert_file
from djengine.tags import TrackMeta, read_tags, square_cover, write_tags


def png_bytes(w=64, h=64, color=(255, 0, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def audio_file_factory(sine_wav, tmp_path):
    from tests.conftest import FakeCtx

    def make(fmt: str):
        dst = tmp_path / f"t_{fmt}.{FORMATS[fmt].ext}"
        asyncio.run(convert_file(FakeCtx(tmp_path / f"j_{fmt}"), sine_wav, dst, ConvertOptions(format=fmt), 3.0))
        return dst

    return make


@pytest.mark.parametrize("fmt", ["mp3", "aac", "alac", "flac", "ogg", "opus", "wav", "aiff"])
def test_roundtrip(fmt, audio_file_factory):
    p = audio_file_factory(fmt)
    write_tags(p, TrackMeta("¿Qué Más Pues?", "J Balvin", "Álbum", "2016", "https://youtu.be/x", bpm=96.0, key="8A"), png_bytes())
    m = read_tags(p)
    assert (m.title, m.artist, m.album, m.year) == ("¿Qué Más Pues?", "J Balvin", "Álbum", "2016")
    assert m.source_url == "https://youtu.be/x"
    assert m.bpm == 96.0 and m.key == "8A"


def test_no_cover_no_bpm(audio_file_factory):
    p = audio_file_factory("mp3")
    write_tags(p, TrackMeta("T", "A"), None)
    m = read_tags(p)
    assert m.title == "T" and m.bpm is None and m.key is None


def test_square_cover():
    out = Image.open(io.BytesIO(square_cover(png_bytes(1280, 720))))
    assert out.size == (600, 600) and out.format == "JPEG"
