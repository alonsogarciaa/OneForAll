import os
from pathlib import Path


def models_dir() -> Path | None:
    d = os.environ.get("ONEFORALL_MODELS")
    return Path(d) if d else None


def ensure_torch_home() -> None:
    """Point torch.hub at the bundled Demucs weights (packaged app works offline)."""
    d = models_dir()
    if d and (d / "torch").is_dir():
        os.environ.setdefault("TORCH_HOME", str(d / "torch"))


def uvr_dir(fallback: Path) -> Path:
    d = models_dir()
    if d and (d / "uvr").is_dir():
        return d / "uvr"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback
