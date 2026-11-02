import os
from pathlib import Path


def models_dir() -> Path | None:
    d = os.environ.get("ONEFORALL_MODELS")
    return Path(d) if d else None


def ensure_torch_home() -> None:
    """Point torch.hub and the HuggingFace cache (demucs loads from HF first) at the bundled weights."""
    d = models_dir()
    if d and (d / "torch").is_dir():
        os.environ.setdefault("TORCH_HOME", str(d / "torch"))
    if d and (d / "hf").is_dir():
        os.environ.setdefault("HF_HOME", str(d / "hf"))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")  # bundled cache: never wait on the network


def uvr_dir(fallback: Path) -> Path:
    d = models_dir()
    if d and (d / "uvr").is_dir():
        return d / "uvr"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback
