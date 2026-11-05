import os

from djengine.stems import models


def test_bundled_caches_are_used_offline(tmp_path, monkeypatch):
    for d in ("torch", "hf"):
        (tmp_path / d).mkdir()
    monkeypatch.setenv("ONEFORALL_MODELS", str(tmp_path))
    for k in ("TORCH_HOME", "HF_HOME", "HF_HUB_OFFLINE"):
        monkeypatch.delenv(k, raising=False)
    models.ensure_torch_home()
    assert os.environ["TORCH_HOME"] == str(tmp_path / "torch")
    assert os.environ["HF_HOME"] == str(tmp_path / "hf")
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_no_bundle_leaves_env_alone(tmp_path, monkeypatch):
    monkeypatch.delenv("ONEFORALL_MODELS", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    models.ensure_torch_home()
    assert "HF_HOME" not in os.environ
