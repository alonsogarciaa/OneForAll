import mutagen
import pytest
from pathlib import Path
from pydantic import ValidationError

from djengine.convert import FORMATS, ConvertOptions, build_ffmpeg_args, convert_file


@pytest.mark.parametrize("fmt", ["mp3", "aac", "alac", "opus", "ogg", "flac", "wav", "aiff"])
async def test_convert_each_format(ctx, sine_wav, tmp_path, fmt):
    dst = tmp_path / f"out.{FORMATS[fmt].ext}"
    await convert_file(ctx, sine_wav, dst, ConvertOptions(format=fmt), 3.0)
    f = mutagen.File(dst)
    assert f is not None and abs(f.info.length - 3.0) < 0.2
    assert ctx.reports and ctx.reports[-1][0] == "converting"


def test_mp3_quality_args():
    a = build_ffmpeg_args(Path("i.wav"), Path("o.mp3"), ConvertOptions(format="mp3", quality="320"))
    assert a[a.index("-b:a") + 1] == "320k"


def test_mp3_v0_args():
    a = build_ffmpeg_args(Path("i.wav"), Path("o.mp3"), ConvertOptions(format="mp3", quality="v0"))
    assert a[a.index("-q:a") + 1] == "0"


def test_24bit_wav():
    a = build_ffmpeg_args(Path("i"), Path("o.wav"), ConvertOptions(format="wav", bit_depth=24, sample_rate=96000))
    assert "pcm_s24le" in a and "96000" in a


def test_rejects_sample_rate_on_lossy():
    with pytest.raises(ValidationError):
        ConvertOptions(format="mp3", sample_rate=96000)


def test_rejects_bad_mp3_quality():
    with pytest.raises(ValidationError):
        ConvertOptions(format="mp3", quality="999")


async def test_bad_input_raises_user_error(ctx, tmp_path):
    from djengine.errors import UserError

    bad = tmp_path / "bad.wav"
    bad.write_text("not audio")
    with pytest.raises(UserError):
        await convert_file(ctx, bad, tmp_path / "o.mp3", ConvertOptions(format="mp3"), None)
