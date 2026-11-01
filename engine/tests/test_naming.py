from djengine.naming import render_name, sanitize_filename, unique_path


def test_strips_illegal_chars():
    assert sanitize_filename('AC/DC - Thunder:struck?') == "ACDC - Thunderstruck"


def test_keeps_accents_and_emoji():
    assert sanitize_filename("¿Qué Más Pues? 🔥") == "¿Qué Más Pues 🔥"


def test_reserved_names():
    assert sanitize_filename("CON") == "CON_"
    assert sanitize_filename("com1") == "com1_"


def test_trailing_dots_spaces_removed_and_length_capped():
    assert sanitize_filename("a. ") == "a"
    assert len(sanitize_filename("x" * 400)) == 180


def test_render_missing_artist():
    assert render_name("{artist} - {title}", {"title": "Song"}) == "Song"


def test_render_empty_gives_placeholder():
    assert render_name("{artist} - {title}", {}) == "Sin título"


def test_collision_same_folder(tmp_path):
    (tmp_path / "A - B.mp3").touch()
    p1 = unique_path(tmp_path, "A - B", "mp3")
    assert p1 == tmp_path / "A - B (1).mp3"
    p1.touch()
    assert unique_path(tmp_path, "A - B", "mp3") == tmp_path / "A - B (2).mp3"
    assert [d for d in tmp_path.iterdir() if d.is_dir()] == []
