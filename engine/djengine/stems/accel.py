"""Which backend separates stems: DirectML only when the ONNX model exists and passed the quality gate."""
import json
from pathlib import Path
from typing import Literal

from .models import models_dir

ONNX_MODEL = "htdemucs_6s.onnx"
VALIDATION = "accel_validated.json"


def onnx_dir() -> Path:
    d = models_dir()
    return (d / "onnx") if d else Path(__file__).resolve().parents[2] / "bench" / "data" / "onnx"


def _providers() -> list[str]:
    try:
        import onnxruntime

        return onnxruntime.get_available_providers()
    except ImportError:
        return []


def _validated(d: Path) -> bool:
    try:
        return bool(json.loads((d / VALIDATION).read_text(encoding="utf-8")).get("passed"))
    except (OSError, ValueError):
        return False


def backend(settings) -> Literal["directml", "cpu"]:
    d = onnx_dir()
    if (
        settings.stems_backend == "auto"
        and (d / ONNX_MODEL).is_file()
        and _validated(d)
        and "DmlExecutionProvider" in _providers()
    ):
        return "directml"
    return "cpu"
