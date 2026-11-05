import json

import pytest

from djengine.settings import Settings
from djengine.stems import accel


@pytest.fixture
def onnx_dir(tmp_path, monkeypatch):
    d = tmp_path / "onnx"
    d.mkdir()
    (d / "htdemucs_6s.onnx").write_bytes(b"x")
    (d / "accel_validated.json").write_text(json.dumps({"passed": True}))
    monkeypatch.setattr(accel, "onnx_dir", lambda: d)
    monkeypatch.setattr(accel, "_providers", lambda: ["DmlExecutionProvider", "CPUExecutionProvider"])
    return d


def test_directml_when_everything_is_in_place(onnx_dir):
    assert accel.backend(Settings()) == "directml"


@pytest.mark.parametrize("breaker", ["setting", "model", "validation", "failed", "provider"])
def test_cpu_when_any_condition_fails(onnx_dir, monkeypatch, breaker):
    s = Settings()
    if breaker == "setting":
        s.stems_backend = "cpu"
    elif breaker == "model":
        (onnx_dir / "htdemucs_6s.onnx").unlink()
    elif breaker == "validation":
        (onnx_dir / "accel_validated.json").unlink()
    elif breaker == "failed":
        (onnx_dir / "accel_validated.json").write_text(json.dumps({"passed": False}))
    else:
        monkeypatch.setattr(accel, "_providers", lambda: ["CPUExecutionProvider"])
    assert accel.backend(s) == "cpu"


def test_backend_endpoint(client):
    assert client.get("/stems/backend", headers={"X-Token": "t"}).json() == {"backend": "cpu"}
