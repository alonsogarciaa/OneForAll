# Fixtures captured 2026-11-09 from public pages, trimmed to a few tracks (structure untouched):
#   spotify_embed_playlist.html  https://open.spotify.com/embed/playlist/37i9dQZF1DXcBWIGoYBM5M
#   spotify_embed_track.html     https://open.spotify.com/embed/track/3zOYmiNOuyDL0ClxJcEJ0T
#   apple_playlist.html          https://music.apple.com/us/playlist/todays-hits/pl.f4d106fed2bd41149aaacabb233eb5eb
#   sc_search.json / sc_set.json yt-dlp --flat-playlist -J "scsearch5:quevedo" (+ one Go+ entry added by hand)
import json
import urllib.error
from pathlib import Path

import pytest

from djengine.discover import links
from djengine.discover.links import parse_link, read_apple, read_soundcloud, read_spotify
from djengine.errors import UserError

FIX = Path(__file__).parent / "fixtures"


def fix(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("text,service,kind,id_", [
    ("https://open.spotify.com/playlist/37i9dQZF1DX0XUsuxWHRQd?si=abc", "spotify", "playlist", "37i9dQZF1DX0XUsuxWHRQd"),
    ("https://open.spotify.com/intl-es/track/4uLU6hMCjMI75M1A2tKUQC", "spotify", "track", "4uLU6hMCjMI75M1A2tKUQC"),
    ("spotify:album:1DFixLWuPkv3KT3TnV35m3", "spotify", "album", "1DFixLWuPkv3KT3TnV35m3"),
    ("  open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3  ", "spotify", "album", "1DFixLWuPkv3KT3TnV35m3"),
    ("https://music.apple.com/es/playlist/x/pl.u-abc", "apple", "playlist", "pl.u-abc"),
    ("https://music.apple.com/es/album/y/123?i=456", "apple", "track", "456"),
    ("https://music.apple.com/es/album/y/123", "apple", "album", "123"),
    ("https://soundcloud.com/artist/sets/name", "soundcloud", "playlist", "artist/sets/name"),
    ("https://soundcloud.com/artist/track-name?utm_source=x", "soundcloud", "track", "artist/track-name"),
])
def test_parse_link(text, service, kind, id_):
    link = parse_link(text)
    assert (link.service, link.kind, link.id) == (service, kind, id_)


def test_parse_link_ignores_youtube_and_text():
    assert parse_link("https://youtu.be/abc") is None
    assert parse_link("la graciosa") is None
    assert parse_link("https://soundcloud.com/artist") is None  # a profile, not a track or set


def test_spotify_link_shortener_is_followed(monkeypatch):
    monkeypatch.setattr(links, "_final_url", lambda u: "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=x")
    link = parse_link("https://spotify.link/AbCdEf")
    assert (link.service, link.kind, link.id) == ("spotify", "playlist", "37i9dQZF1DXcBWIGoYBM5M")


def test_read_spotify_playlist_fixture():
    lst = read_spotify(parse_link("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"),
                       fetch=lambda u: fix("spotify_embed_playlist.html"))
    assert lst.service == "spotify" and lst.name and len(lst.items) == 4 and not lst.truncated
    assert all(i.title and i.artist and i.duration_s for i in lst.items)
    assert lst.items[0].title == "Stop The Wedding!" and lst.items[0].artist == "Ashe" and lst.items[0].duration_s == 199


def test_read_spotify_fetches_the_embed_page():
    seen = []
    read_spotify(parse_link("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"),
                 fetch=lambda u: seen.append(u) or fix("spotify_embed_playlist.html"))
    assert seen == ["https://open.spotify.com/embed/playlist/37i9dQZF1DXcBWIGoYBM5M"]


def test_read_spotify_track_fixture():
    lst = read_spotify(parse_link("https://open.spotify.com/track/3zOYmiNOuyDL0ClxJcEJ0T"),
                       fetch=lambda u: fix("spotify_embed_track.html"))
    assert [(i.title, i.artist, i.duration_s) for i in lst.items] == [("Stop The Wedding!", "Ashe", 199)]


def test_spotify_100_tracks_is_flagged_as_truncated():
    s = fix("spotify_embed_playlist.html")
    head, body = s.split('application/json">', 1)
    data, tail = body.split("</script>", 1)
    d = json.loads(data)
    tl = d["props"]["pageProps"]["state"]["data"]["entity"]["trackList"]
    d["props"]["pageProps"]["state"]["data"]["entity"]["trackList"] = (tl * 25)[:100]
    lst = read_spotify(parse_link("spotify:playlist:x"), fetch=lambda u: head + 'application/json">' + json.dumps(d) + "</script>" + tail)
    assert lst.truncated and len(lst.items) == 100


def test_read_apple_playlist_fixture():
    lst = read_apple(parse_link("https://music.apple.com/us/playlist/todays-hits/pl.f4d106fed2bd41149aaacabb233eb5eb"),
                     fetch=lambda u: fix("apple_playlist.html"))
    assert lst.service == "apple" and lst.name.endswith("Hits") and len(lst.items) == 4
    assert lst.items[0].title == "Choosin' Texas" and lst.items[0].artist == "Ella Langley" and lst.items[0].duration_s == 232


def test_read_soundcloud_set():
    data = json.loads(fix("sc_set.json"))
    lst = read_soundcloud(parse_link("https://soundcloud.com/artist/sets/name"), run=lambda url: data)
    assert lst.service == "soundcloud" and lst.name == "Mi set de prueba" and len(lst.items) == 3
    assert all(i.url and i.url.startswith("https://") for i in lst.items)


@pytest.mark.parametrize("reader,url,msg", [
    (read_spotify, "spotify:playlist:x", "Spotify ha cambiado; actualiza la app"),
    (read_apple, "https://music.apple.com/es/playlist/x/pl.u-abc", "Apple Music ha cambiado; actualiza la app")])
def test_changed_page_is_a_clear_error(reader, url, msg):
    with pytest.raises(UserError) as e:
        reader(parse_link(url), fetch=lambda u: "<html></html>")
    assert (e.value.code, e.value.message) == ("source_changed", msg)


def test_unreachable_link_is_a_clear_error():
    def gone(u):
        raise urllib.error.HTTPError(u, 404, "Not Found", {}, None)

    with pytest.raises(UserError) as e:
        read_spotify(parse_link("spotify:playlist:x"), fetch=gone)
    assert (e.value.code, e.value.message) == ("bad_link", "No se pudo leer el enlace")
