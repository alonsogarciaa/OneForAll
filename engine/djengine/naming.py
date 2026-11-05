import re
from pathlib import Path

MAX_NAME_LEN = 180
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def sanitize_filename(name: str) -> str:
    name = _ILLEGAL.sub("", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    name = name[:MAX_NAME_LEN].rstrip(". ")
    if name.upper() in _RESERVED:
        name += "_"
    return name


def render_name(template: str, meta: dict[str, str]) -> str:
    out = _PLACEHOLDER.sub(lambda m: str(meta.get(m.group(1)) or ""), template)
    # drop separators left dangling by empty fields, e.g. " - Song" or "Artist - "
    out = re.sub(r"^[\s\-–_·|,]+|[\s\-–_·|,]+$", "", out)
    out = re.sub(r"\s+[\-–_·|]\s+[\-–_·|]\s+", " - ", out)
    out = sanitize_filename(out)
    return out or "Sin título"


MAX_PATH_LEN = 250  # Windows MAX_PATH is 260; keep room for " (n)"


def unique_path(directory: Path, stem: str, ext: str) -> Path:
    directory = Path(directory)
    room = MAX_PATH_LEN - len(str(directory)) - 1 - len(ext) - 1 - 5
    if room < len(stem):
        stem = stem[:max(room, 1)].rstrip(". ") or "_"
    candidate = directory / f"{stem}.{ext}"
    n = 1
    while candidate.exists():
        candidate = directory / f"{stem} ({n}).{ext}"
        n += 1
    return candidate
