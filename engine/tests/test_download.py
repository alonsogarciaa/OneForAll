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


@pytest.mark.parametrize("url", [
    "file:///C:/Windows/win.ini",
    "http://i.ytimg.com/vi/x/hq.jpg",
    "https://127.0.0.1:8000/secret",
    "https://evil.example.com/x.jpg",
    "https://i.ytimg.com.evil.com/x.jpg",
])
def test_thumbnail_rejects_non_youtube_urls(url, monkeypatch):
    from djengine import download

    opened = []
    monkeypatch.setattr(download._opener, "open", lambda *a, **k: opened.append(a))
    assert download.fetch_thumbnail(url) is None
    assert opened == []


def test_thumbnail_allows_youtube_hosts():
    from djengine.download import thumbnail_url_allowed

    assert thumbnail_url_allowed("https://i.ytimg.com/vi/x/hq.jpg")
    assert thumbnail_url_allowed("https://yt3.googleusercontent.com/abc=s576")
    assert thumbnail_url_allowed("https://lh3.ggpht.com/abc")


def test_thumbnail_redirect_to_other_host_is_refused():
    import urllib.error
    import urllib.request

    from djengine.download import SafeRedirect

    req = urllib.request.Request("https://i.ytimg.com/vi/x/hq.jpg")
    h = SafeRedirect()
    with pytest.raises(urllib.error.HTTPError):
        h.redirect_request(req, None, 302, "Found", {}, "http://169.254.169.254/latest")
    assert h.redirect_request(req, None, 302, "Found", {}, "https://i.ytimg.com/vi/y/hq.jpg") is not None
