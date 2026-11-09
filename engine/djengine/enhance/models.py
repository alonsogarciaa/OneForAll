"""Apollo weights: the official checkpoint (pinned SHA-256) converted once to safetensors, which loads without pickle.

Order: bundled ONEFORALL_MODELS/apollo/apollo.safetensors, then the user cache, then convert a bundled or
downloaded pytorch_model.bin into the cache.
"""
import hashlib
import logging
import pickle
import types
import urllib.request
from pathlib import Path

from ..errors import UserError
from ..stems.models import models_dir

log = logging.getLogger(__name__)
FILE = "pytorch_model.bin"
SAFE = "apollo.safetensors"
URL = "https://huggingface.co/JusperLee/Apollo/resolve/main/pytorch_model.bin"
SHA256 = "99d9af7f1ff20e63c393035513a655392818d66b4d7fc23d658175c1f15e8d76"
MISSING = UserError("model_missing", "No se pudo descargar el modelo de mejora")

_SAFE_BUILTINS = {"dict", "list", "tuple", "set", "frozenset", "int", "float", "str", "bool", "bytes", "bytearray", "slice", "complex", "long", "unicode"}


class _Stub(dict):
    """Stands in for omegaconf configs in the checkpoint's metadata (never used)."""

    def __setstate__(self, state):
        pass


class _Restricted(pickle.Unpickler):
    """Only tensors and plain containers: the checksum is verified first, and nothing that can run code is allowed."""

    def find_class(self, module, name):
        root = module.split(".")[0]
        if root in ("omegaconf", "typing"):
            return _Stub
        if root in ("builtins", "__builtin__") and name in _SAFE_BUILTINS:
            return super().find_class(module, name)
        if (root == "collections" and name in ("OrderedDict", "defaultdict")) or root in ("torch", "_codecs") or module.startswith("numpy"):
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"blocked {module}.{name}")


def _cache_dir() -> Path:
    from ..app_paths import default_root

    return default_root() / "models" / "apollo"


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def convert(src: Path, dst: Path) -> Path:
    """Checksum the official checkpoint, read only its tensors with a restricted unpickler, write safetensors."""
    import torch
    from safetensors.torch import save_file

    if _sha(src) != SHA256:
        raise OSError(f"checksum mismatch for {src}")
    pm = types.SimpleNamespace(Unpickler=_Restricted, load=pickle.load, __name__="restricted")
    conf = torch.load(src, map_location="cpu", weights_only=False, pickle_module=pm)
    sd = {k: v.contiguous() for k, v in conf["state_dict"].items()}
    tmp = dst.with_suffix(".part")
    save_file(sd, str(tmp))
    tmp.replace(dst)
    return dst


def _download(dst: Path) -> None:
    tmp = dst.with_suffix(".part")
    try:
        with urllib.request.urlopen(URL, timeout=60) as r, open(tmp, "wb") as f:
            while block := r.read(1 << 20):
                f.write(block)
        tmp.replace(dst)
    finally:
        tmp.unlink(missing_ok=True)


def apollo_path() -> Path:
    d = models_dir()
    bundled = d / "apollo" if d else None
    if bundled and (bundled / SAFE).is_file():
        return bundled / SAFE
    cache = _cache_dir()
    if (cache / SAFE).is_file():
        return cache / SAFE
    try:
        cache.mkdir(parents=True, exist_ok=True)
        src = bundled / FILE if bundled and (bundled / FILE).is_file() else cache / FILE
        if not src.is_file():
            _download(src)
        return convert(src, cache / SAFE)
    except OSError as e:
        log.warning("apollo model unavailable: %s", e)
        raise MISSING
