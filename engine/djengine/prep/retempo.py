"""retempo job: a new copy of a track at another BPM and key, rendered with rubberband and already analysed."""
import asyncio
import logging
from dataclasses import replace
from pathlib import Path

import numpy as np

from ..analysis.camelot import camelot_shift, from_camelot, tag_key
from ..analysis.config import ANALYSIS_VERSION
from ..analysis.store import AnalysisRecord, file_stamp, now_iso
from ..convert import ffmpeg_error
from ..errors import UserError
from ..library import TrackRecord
from ..mixer.export import _CODEC
from ..naming import unique_path
from ..stems.names import ext_for
from ..stems.runner import _duration
from ..tags import TrackMeta, read_cover, read_tags, set_bpm_key, write_tags
from ..tools import find_tool
from .grid import Grid, beats
from .sections import Section

log = logging.getLogger(__name__)
MIN_RATIO, MAX_RATIO = 0.5, 1.5
_BY_SUFFIX = {".wav": "wav16", ".flac": "flac", ".mp3": "mp3"}


def _extra_args() -> list[str]:
    return []  # seam for tests (slow renders)


def retempo_name(stem: str, src_bpm: float, bpm: float, src_camelot: str | None, semis: int) -> str:
    """«Song (124 BPM, 9A)»; a part is left out when it did not change."""
    tags = []
    if round(bpm, 1) != round(src_bpm, 1):
        tags.append(f"{round(bpm, 1):g} BPM")
    if semis and src_camelot:
        tags.append(camelot_shift(src_camelot, semis))
    elif semis:
        tags.append(f"{semis:+d}")
    return f"{stem} ({', '.join(tags)})" if tags else f"{stem} (copia)"


def default_format(path: Path) -> str:
    return _BY_SUFFIX.get(path.suffix.lower(), "flac")


def check_range(src_bpm: float, bpm: float) -> None:
    if not src_bpm or not (MIN_RATIO - 1e-9 <= bpm / src_bpm <= MAX_RATIO + 1e-9):
        raise UserError("bad_request", "El BPM destino debe estar entre el 50 % y el 150 % del original")


def _light_analysis(svc, src_rec: AnalysisRecord, src_side: dict, out: Path, ratio: float, bpm: float, semis: int):
    """BPM, key, grid and sections come from the source (scaled); only loudness and the waveform are measured."""
    from ..analysis.audio_io import decode
    from ..analysis.loudness import measure
    from ..analysis.waveform import compute

    stereo = decode(out, sr=44100, mono=False)
    lufs, peak = measure(stereo, 44100)
    import librosa

    mono = stereo.mean(axis=0).astype(np.float32)
    y = librosa.resample(mono, orig_sr=44100, target_sr=22050) if mono.size else mono
    wf = compute(y, 22050)
    duration = round(len(y) / 22050, 3)
    camelot = camelot_shift(src_rec.camelot, semis) if src_rec.camelot else None
    tonic, mode = from_camelot(camelot) if camelot else (src_rec.tonic, src_rec.mode)
    size, mtime = file_stamp(out)
    rec = replace(src_rec, path=str(out), size=size, mtime=mtime, bpm=round(bpm, 1), bpm_source="manual",
                  tonic=tonic, mode=mode, camelot=camelot, lufs=lufs, peak_db=peak,
                  version=ANALYSIS_VERSION, created_at=now_iso())
    g = svc.analysis.get_grid(Path(src_rec.path)) or Grid(0.0, src_rec.bpm or bpm)
    grid = Grid(round(g.anchor / ratio, 4), round(bpm, 1), "manual")
    sections = [Section(round(s["start"] / ratio, 3), round(s["end"] / ratio, 3), s["label"], s.get("source", "auto"))
                for s in src_side.get("sections") or []]
    svc.analysis.save(rec, {"beats": beats(grid, duration), "grid": grid.to_dict(), "grid_auto": grid.to_dict(),
                            "sections": [s.to_dict() for s in sections],
                            "sections_auto": [s.to_dict() for s in sections],
                            "waveform": wf, "duration": duration})
    return rec


def make_retempo_runner(svc, path: Path, bpm: float, semis: int, fmt: str | None):
    path = Path(path)

    async def run(ctx) -> dict:
        src = svc.analysis.get(path)
        if not path.is_file() or src is None or not src.bpm:
            raise UserError("not_analyzed", "Analiza primero")
        grid_src = svc.analysis.get_grid(path)
        base_bpm = float(grid_src.bpm) if grid_src and grid_src.bpm else float(src.bpm)  # the grid is the exact tempo
        check_range(base_bpm, bpm)
        if not -12 <= semis <= 12:
            raise UserError("bad_request", "El cambio de tono va de −12 a +12 semitonos")
        side = svc.analysis.read_sidecar(path) or {}
        ratio = bpm / base_bpm
        f = fmt or default_format(path)
        ext = ext_for(f)
        tmp = ctx.tmp_dir / f"retempo.{ext}"
        total = (_duration(path) or 0.0) / ratio
        flt = f"rubberband=tempo={ratio:.6f}:pitch={2 ** (semis / 12):.6f}:pitchq=quality:transients=mixed"
        ctx.report("rendering", 0)
        proc = await asyncio.create_subprocess_exec(
            find_tool("ffmpeg"), "-v", "error", "-nostdin", "-y", *_extra_args(), "-i", str(path),
            "-map", "0:a:0", "-af", flt, "-ar", "44100", "-ac", "2", *_CODEC[f],
            "-progress", "pipe:1", "-nostats", str(tmp),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        ctx.register_process(proc)
        err_task = asyncio.create_task(proc.stderr.read())
        async for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("out_time_us=") and total:
                try:
                    ctx.report("rendering", min(95.0, int(line.split("=", 1)[1]) / 1e6 / total * 95))
                except ValueError:
                    continue
        await proc.wait()
        stderr = (await err_task).decode("utf-8", "replace")
        ctx.check_cancelled()
        if proc.returncode != 0:
            log.warning("retempo failed (%s): %s", proc.returncode, stderr[-2000:])
            raise ffmpeg_error(stderr)

        ctx.begin_finalize()
        ctx.report("analysing", 96)
        from ..pipelines import _commit

        track = svc.library.track_by_path(str(path))
        try:
            meta = read_tags(path)
        except Exception:
            meta = TrackMeta(track.title if track else path.stem, track.artist if track else "")
        try:
            cover = read_cover(path)
        except Exception:
            cover = None
        name = retempo_name(path.stem, base_bpm, bpm, src.camelot, semis)
        final = unique_path(path.parent, name, ext)
        await asyncio.to_thread(_commit, tmp, final)
        title = retempo_name(meta.title or path.stem, base_bpm, bpm, src.camelot, semis)
        try:
            write_tags(final, TrackMeta(title, meta.artist, meta.album, meta.year, meta.source_url), cover)
        except Exception as e:  # e.g. a format mutagen cannot tag: the audio still counts
            log.info("tags not written for %s: %s", final.name, e)
        rec = await asyncio.to_thread(_light_analysis, svc, src, side, final, ratio, bpm, semis)
        try:
            key = tag_key(rec.tonic, rec.mode, svc.settings.key_notation) if rec.tonic and rec.mode else None
            set_bpm_key(final, rec.bpm, key)
        except Exception as e:
            log.info("bpm/key tags not written for %s: %s", final.name, e)
        svc.analysis.restamp(final)
        svc.library.add_track(TrackRecord(None, None, title, meta.artist or (track.artist if track else ""),
                                          meta.album or "", int(total) or None, None, str(final), ext, None, None, ""))
        musical = tag_key(rec.tonic, rec.mode, "musical") if rec.tonic and rec.mode else None
        svc.library.set_track_analysis(str(final), rec.bpm, musical, rec.camelot, rec.lufs)
        svc.library.add_history(None, title, meta.artist or "", "retempo", "done")
        return {"path": str(final)}

    return run
