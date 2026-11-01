import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "OneForAll"


def default_root() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


@dataclass(frozen=True)
class AppPaths:
    root: Path
    db_path: Path
    settings_path: Path
    tmp_dir: Path
    logs_dir: Path
    models_dir: Path

    @classmethod
    def from_root(cls, root: Path) -> "AppPaths":
        root = Path(root)
        p = cls(
            root=root,
            db_path=root / "library.db",
            settings_path=root / "settings.json",
            tmp_dir=root / "tmp",
            logs_dir=root / "logs",
            models_dir=root / "models",
        )
        for d in (p.root, p.tmp_dir, p.logs_dir, p.models_dir):
            d.mkdir(parents=True, exist_ok=True)
        return p
