import os
import shutil
from pathlib import Path
from typing import Literal

from .errors import UserError

Tool = Literal["ffmpeg", "ffprobe", "yt-dlp"]


def find_tool(name: Tool) -> str:
    """Bundled tools dir (ONEFORALL_TOOLS) first, then PATH."""
    tools_dir = os.environ.get("ONEFORALL_TOOLS")
    if tools_dir:
        for candidate in (Path(tools_dir) / f"{name}.exe", Path(tools_dir) / name):
            if candidate.is_file():
                return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    raise UserError("internal", f"Falta {name}")
