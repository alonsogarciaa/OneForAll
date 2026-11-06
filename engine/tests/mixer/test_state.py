import os
import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from djengine.app_paths import AppPaths
from djengine.mixer.state import MixerStore, MixState, StemState, audible, effective_semis
from djengine.server import build_services, create_app

H = {"X-Token": "t"}


def test_defaults_and_ranges():
    s = MixState()
    assert s.rate == 1.0 and s.semis == 0 and s.master == 1.0 and s.loop is None and not s.metronome.on
    with pytest.raises(ValidationError):
        MixState(rate=0.49)
    with pytest.raises(ValidationError):
        MixState(semis=13)


def test_unknown_stem_rejected():
    with pytest.raises(ValidationError):
        MixState(stems={"kazoo": StemState()})


def test_loop_end_after_start():
    with pytest.raises(ValidationError):
        MixState(loop={"start": 5, "end": 5})


def test_effective_semis_clamped():
    s = MixState(semis=10, stems={"vocals": StemState(semis=5)})
    assert effective_semis(s, "vocals") == 12
    assert effective_semis(s, "drums") == 10


def test_audible_solo_then_mute():
    names = ["vocals", "drums", "bass"]
    assert audible(MixState(stems={"drums": StemState(solo=True)}), names) == ["drums"]
    assert audible(MixState(stems={"vocals": StemState(mute=True)}), names) == ["drums", "bass"]


@pytest.mark.skipif(os.name != "nt", reason="case-insensitive paths")
def test_store_roundtrip_case_insensitive(tmp_path):
    st = MixerStore(tmp_path / "db")
    st.put(r"C:\X\Song.wav", MixState(rate=0.75))
    assert st.get(r"C:\X\SONG.WAV").rate == 0.75


def test_corrupt_row_returns_none(tmp_path):
    st = MixerStore(tmp_path / "db")
    st.put(tmp_path / "a.wav", MixState())
    c = sqlite3.connect(tmp_path / "db")
    c.execute("UPDATE mixer_state SET state_json='{bad'")
    c.commit()
    assert st.get(tmp_path / "a.wav") is None


def test_api_get_put(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEFORALL_FAKE_DELAY", "0")
    svc = build_services(AppPaths.from_root(tmp_path / "data"), fake=True)
    with TestClient(create_app(svc, token="t")) as c:
        p = str(tmp_path / "song.wav")
        assert c.get("/mixer/state", params={"path": p}, headers=H).json() == {"state": None}
        assert c.put("/mixer/state", json={"path": p, "state": {"rate": 0.8}}, headers=H).json() == {"ok": True}
        assert c.get("/mixer/state", params={"path": p}, headers=H).json()["state"]["rate"] == 0.8
        assert c.put("/mixer/state", json={"path": p, "state": {"rate": 2}}, headers=H).status_code == 422
