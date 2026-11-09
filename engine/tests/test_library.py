import sqlite3

import pytest

from djengine.library import Library, TrackRecord, normalize_key


@pytest.fixture
def lib(tmp_path):
    return Library(tmp_path / "library.db")


def rec(**kw) -> TrackRecord:
    base = dict(
        id=None, video_id=None, title="T", artist="A", album="", duration_s=200, views=None,
        path="C:/x.mp3", format="mp3", bitrate=320, cover_path=None, added_at="",
    )
    base.update(kw)
    return TrackRecord(**base)


def columns(lib: Library, table: str) -> set[str]:
    with sqlite3.connect(lib.db_path) as c:
        return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}


def test_normalize_key_strips_noise():
    assert normalize_key("Quevedo", "La Graciosa (Official Video)") == normalize_key("quevedo", "la graciosa")
    assert normalize_key("Bad Bunny", "Song ft. Drake") == normalize_key("Bad Bunny", "Song")
    assert normalize_key("Rosalía", "Despechá") == normalize_key("Rosalia", "Despecha")


def test_duplicate_by_video_id_and_by_name(lib, tmp_path):
    f = tmp_path / "q.mp3"
    f.write_bytes(b"x")
    lib.add_track(rec(video_id="abc", artist="Quevedo", title="La Graciosa", path=str(f)))
    assert lib.find_duplicate("abc", "", "") is not None
    assert lib.find_duplicate("zzz", "QUEVEDO", "La Graciosa (Lyrics)") is not None
    assert lib.find_duplicate("zzz", "Other", "Song") is None


def test_history_delete_selected_and_all(lib):
    ids = [lib.add_history("v%d" % i, "t", "a", "download", "done") for i in range(3)]
    assert lib.delete_history([ids[0]]) == 1 and len(lib.list_history()) == 2
    assert lib.delete_history(None) == 2 and lib.list_history() == []


def test_refresh_missing_marks_not_deletes(lib, tmp_path):
    lib.add_track(rec(path=str(tmp_path / "gone.mp3")))
    assert lib.refresh_missing() == 1
    assert lib.list_tracks()[0].missing is True


def test_bpm_key_columns_exist(lib):
    assert lib.list_tracks() == [] and {"bpm", "musical_key", "camelot"} <= columns(lib, "tracks")


def test_list_tracks_filters_by_query(lib):
    lib.add_track(rec(title="La Graciosa", artist="Quevedo", video_id="1"))
    lib.add_track(rec(title="Otra", artist="Nadie", video_id="2"))
    assert [t.title for t in lib.list_tracks("graci")] == ["La Graciosa"]


def test_playlist_tracks(lib):
    tid = lib.add_track(rec(video_id="1"))
    pid = lib.add_playlist("PL1", "Mi lista", "C:/m/Mi lista")
    lib.add_playlist_track(pid, tid, 0)
    with sqlite3.connect(lib.db_path) as c:
        assert c.execute("SELECT COUNT(*) FROM playlist_tracks").fetchone()[0] == 1


def test_deleted_file_is_not_a_duplicate(lib, tmp_path):
    lib.add_track(rec(video_id="abc", artist="Quevedo", title="La Graciosa", path=str(tmp_path / "gone.mp3")))
    assert lib.find_duplicate("abc", "Quevedo", "La Graciosa") is None


def test_phase4b_migration_is_idempotent(tmp_path):
    Library(tmp_path / "l.db")
    lib = Library(tmp_path / "l.db")
    assert {"enhanced", "origin_video_id"} <= columns(lib, "tracks")


def test_video_source_and_enhanced(lib):
    lib.add_track(rec(video_id="abc", path="C:/a.mp3"))
    lib.add_track(rec(path="C:/a (124 BPM).mp3", origin_video_id="abc"))
    lib.add_track(rec(path="C:/own.mp3"))
    assert lib.video_source(lib.track_by_path("C:/a.mp3")) == "abc"
    assert lib.video_source(lib.track_by_path("C:/a (124 BPM).mp3")) == "abc"
    assert lib.video_source(lib.track_by_path("C:/own.mp3")) is None
    lib.set_enhanced("C:/a.mp3")
    assert lib.track_by_path("C:/a.mp3").enhanced is True


def test_update_track_path_keeps_analysis(lib):
    lib.add_track(rec(path="C:/a.mp3"))
    lib.set_track_analysis("C:/a.mp3", 128.0, "A minor", "8A", -9.0)
    lib.update_track_path("C:/a.mp3", "C:/a.flac", "flac")
    t = lib.track_by_path("C:/a.flac")
    assert t and t.format == "flac" and t.bpm == 128.0 and t.camelot == "8A"
    assert lib.track_by_path("C:/a.mp3") is None
