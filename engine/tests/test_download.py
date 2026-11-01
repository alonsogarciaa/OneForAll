import sys
from pathlib import Path

import pytest

from djengine.download import download_audio, map_ytdlp_error, parse_progress
from djengine.errors import ERROR_MESSAGES, UserError

FAKE = Path(__file__).parent / "fixtures" / "fake_ytdlp.py"


def test_parse_progress():
    assert parse_progress("[download]  42.3% of ~4.20MiB at 1.21MiB/s ETA 00:03") == (42.3, "1.21MiB/s", "00:03")
    assert parse_progress("[download] 100% of 4.20MiB in 00:00:02") == (100.0, None, None)
    assert parse_progress("[info] something") is None


@pytest.mark.parametrize("stderr,code", [
    ("ERROR: [youtube] x: Private video", "unavailable"),
    ("ERROR: [youtube] x: Video unavailable", "unavailable"),
    ("ERROR: Sign in to confirm your age", "blocked"),
    ("ERROR: The uploader has not made this video available in your country", "blocked"),
    ("urlopen error [Errno 11001] getaddrinfo failed", "offline"),
    ("OSError: [Errno 28] No space left on device", "disk"),
    ("ERROR: Unable to extract nsig function", "extractor_outdated"),
    ("something nobody expected", "extractor_outdated"),
])
def test_error_mapping(stderr, code):
    e = map_ytdlp_error(stderr)
    assert e.code == code and e.message == ERROR_MESSAGES[code]


def test_error_messages_exact():
    assert ERROR_MESSAGES == {
        "unavailable": "Este vídeo ya no está disponible",
        "blocked": "YouTube bloquea este vídeo (edad/región)",
        "offline": "Sin conexión",
        "extractor_outdated": "YouTube ha cambiado; actualiza yt-dlp",
        "disk": "No se puede escribir en la carpeta de destino",
    }


async def test_download_with_fake_ytdlp(ctx, monkeypatch):
    monkeypatch.setenv("ONEFORALL_YTDLP", f'"{sys.executable}" "{FAKE}"')
    p = await download_audio(ctx, "https://youtu.be/ok")
    assert p.name.startswith("src.") and p.parent == ctx.tmp_dir
    pcts = [r[1] for r in ctx.reports if r[0] == "downloading"]
    assert pcts[-1] == 100.0 and 57.5 in pcts


async def test_download_failure_maps(ctx, monkeypatch):
    monkeypatch.setenv("ONEFORALL_YTDLP", f'"{sys.executable}" "{FAKE}"')
    with pytest.raises(UserError) as ei:
        await download_audio(ctx, "https://youtu.be/private")
    assert ei.value.code == "unavailable"
