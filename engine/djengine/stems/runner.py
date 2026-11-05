import asyncio
import contextlib
import logging
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from ..analysis.audio_io import decode
from ..errors import UserError
from ..tags import read_tags
from ..tools import find_tool
from .names import KARAOKE, STEMS, ext_for, stems_folder
from .separate import get_separator

log = logging.getLogger(__name__)
SR = 44100
MAX_SECONDS = 20 * 60  # whole-song arrays: ~2 GB of RAM per 10 min of audio
_SUBTYPE = {"wav16": "PCM_16", "wav24": "PCM_24", "flac": "PCM_16"}


def _meta(svc, path: Path) -> dict:
    track = svc.library.track_by_path(str(path))
    if track:
        return {"artist": track.artist, "title": track.title, "album": track.album}
    try:
        t = read_tags(path)
        if t.title:
            return {"artist": t.artist, "title": t.title, "album": t.album}
    except Exception:
        pass
    return {"artist": "", "title": path.stem, "album": ""}


def _duration(path: Path) -> float | None:
    try:
        import mutagen

        f = mutagen.File(path)
        if f is not None and f.info and f.info.length:
            return float(f.info.length)
        return sf.info(str(path)).duration
    except Exception:
        return None


def _folder_for(svc, path: Path) -> Path:
    """Existing folder of this source, else <Artist - Title>, else <Artist - Title> (n) if another source owns it."""
    existing = svc.stems.folder_for(path)
    if existing is not None:
        return existing
    base = stems_folder(svc.settings, _meta(svc, path))
    candidate, n = base, 1
    while svc.stems.sources_in_folder(candidate) - {str(path)}:
        candidate = base.with_name(f"{base.name} ({n})")
        n += 1
    return candidate


def _encode(y: np.ndarray, dst: Path, fmt: str) -> None:
    data = np.clip(y.T, -1.0, 1.0)
    if fmt == "mp3":
        wav = dst.with_suffix(".tmp.wav")
        sf.write(wav, data, SR, subtype="PCM_16")
        proc = subprocess.run([find_tool("ffmpeg"), "-v", "error", "-nostdin", "-y", "-i", str(wav),
                               "-c:a", "libmp3lame", "-b:a", "320k", str(dst)], capture_output=True)
        wav.unlink(missing_ok=True)
        if proc.returncode != 0:
            raise UserError("internal", "No se pudo codificar el stem")
    else:
        sf.write(dst, data, SR, subtype=_SUBTYPE[fmt], format="FLAC" if fmt == "flac" else "WAV")


def _work(svc, ctx, path: Path, todo: list[str], karaoke: bool, fmt: str, cached: dict) -> dict[str, Path]:
    """Blocking part (runs in a thread): decode, separate, optional karaoke, encode into tmp."""
    ctx.report("loading_model", 0)
    separator = get_separator(svc)
    if all(s in KARAOKE for s in todo) and "vocals" in cached:
        # only the lead/backing split is missing: reuse the cached vocals, skip Demucs
        stems = {"vocals": decode(cached["vocals"], sr=SR, mono=False)}
    else:
        audio = decode(path, sr=SR, mono=False)
        ctx.check_cancelled()
        ctx.report("separating", 5)
        stems = separator.separate(audio, SR, lambda f: ctx.report("separating", 5 + 75 * f), lambda: ctx.cancelled)
    ctx.check_cancelled()
    if karaoke:
        from .karaoke import get_karaoke  # Task 4

        ctx.report("karaoke", 80)
        lead, backing = get_karaoke(svc, separator).split(stems["vocals"], SR, ctx.tmp_dir)
        stems["lead_vocals"], stems["backing_vocals"] = lead, backing
        ctx.check_cancelled()
    ctx.report("encoding", 88)
    out = {}
    for stem in todo:
        dst = ctx.tmp_dir / f"{stem}.{ext_for(fmt)}"
        _encode(stems[stem], dst, fmt)
        out[stem] = dst
        ctx.check_cancelled()
    return out


def make_stems_runner(svc, path: Path, wanted: list[str], karaoke: bool = False):
    path = Path(path)
    wanted = list(dict.fromkeys(wanted + (["vocals"] if karaoke else [])))
    wanted_all = wanted + (list(KARAOKE) if karaoke else [])

    async def run(ctx) -> dict:
        if not path.is_file():
            raise UserError("unreadable", "No se puede leer el audio de este archivo")
        unknown = [s for s in wanted if s not in STEMS]
        if unknown:
            raise UserError("internal", f"Stem desconocido: {unknown[0]}")
        cached = svc.stems.get(path)
        folder = _folder_for(svc, path)
        todo = [s for s in wanted_all if s not in cached]
        if not todo:
            return {"path": str(path), "folder": str(folder), "stems": {s: str(cached[s]) for s in wanted_all}}

        seconds = _duration(path)
        if seconds is not None and seconds > MAX_SECONDS:
            raise UserError("too_long", f"La separación admite pistas de hasta {MAX_SECONDS // 60} minutos")

        fmt = svc.settings.stems_format
        work = asyncio.ensure_future(asyncio.to_thread(_work, svc, ctx, path, todo, karaoke, fmt, cached))
        try:
            produced = await asyncio.shield(work)
        except asyncio.CancelledError:
            # the thread cannot be killed: wait until it notices (or finishes) before tmp/ is removed
            ctx.cancelled = True
            with contextlib.suppress(BaseException):
                await work
            raise

        ctx.begin_finalize()
        ctx.report("saving", 96)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise UserError("disk", "No se puede escribir en la carpeta de stems")
        model = get_separator(svc).name
        result = {s: str(cached[s]) for s in wanted_all if s in cached}
        from ..pipelines import _commit

        for stem, tmp_file in produced.items():
            final = folder / tmp_file.name
            await asyncio.to_thread(_commit, tmp_file, final)  # atomic; cross-drive copies go through a .part file
            for old in folder.glob(f"{stem}.*"):  # same stem left over in another format
                if old.suffix != final.suffix and old.suffix in (".wav", ".flac", ".mp3"):
                    old.unlink(missing_ok=True)
            svc.stems.add(path, stem, final, model)
            result[stem] = str(final)
        return {"path": str(path), "folder": str(folder), "stems": result}

    return run
