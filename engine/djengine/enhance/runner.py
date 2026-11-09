"""enhance job: restore a track with Apollo, as a new copy or in place of the original (kept in Originales/)."""
import asyncio
import contextlib
import errno
import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf

from ..analysis.store import file_stamp, now_iso
from ..convert import ffmpeg_error
from ..errors import JobCancelled, UserError, user_error
from ..library import TrackRecord
from ..naming import unique_path
from ..pipelines import _commit
from ..tags import TrackMeta, copy_tags, read_cover, read_tags, set_bpm_key, write_tags
from ..tools import find_tool
from .apollo import SR, get_restorer, load_audio

log = logging.getLogger(__name__)
Mode = Literal["copy", "replace"]
Fmt = Literal["same", "flac"]
BUSY = UserError("file_busy", "Archivo en uso: ciérralo en tu programa DJ")
_LOSSY = {".mp3": ("mp3", ["-c:a", "libmp3lame", "-b:a", "320k"]),
          ".m4a": ("m4a", ["-c:a", "aac", "-b:a", "320k"]),
          ".aac": ("m4a", ["-c:a", "aac", "-b:a", "320k"]),
          ".opus": ("opus", ["-c:a", "libopus", "-b:a", "256k"]),
          ".ogg": ("ogg", ["-c:a", "libvorbis", "-q:a", "10"])}
_FLAC24 = ["-c:a", "flac", "-sample_fmt", "s32"]


def _chunk_delay() -> float:
    return 0.0  # seam for tests (slow restores to cancel mid-way)


def enhanced_name(stem: str) -> str:
    return f"{stem} (Mejorado)"


def probe(path: Path) -> tuple[str, int | None]:
    """Codec name and bits per sample of the first audio stream."""
    r = subprocess.run([find_tool("ffprobe"), "-v", "error", "-select_streams", "a:0", "-show_entries",
                        "stream=codec_name,bits_per_raw_sample,bits_per_sample,sample_fmt", "-of", "json", str(path)],
                       capture_output=True, text=True)
    try:
        s = json.loads(r.stdout)["streams"][0]
    except (ValueError, KeyError, IndexError):
        return "", None
    vals = [str(s.get(k, "")) for k in ("bits_per_raw_sample", "bits_per_sample")]
    bits = next((int(v) for v in vals if v.isdigit() and int(v) > 0), None)
    if bits is None and s.get("sample_fmt", "").startswith(("s32", "flt")):
        bits = 24
    return s.get("codec_name", ""), bits


def target_codec(path: Path, fmt: Fmt, probed: tuple[str, int | None] | None = None) -> tuple[str, list[str]]:
    """Extension and ffmpeg codec args: lossy stays lossy at 320 kbps, lossless keeps its bit depth."""
    if fmt == "flac":
        return "flac", list(_FLAC24)
    suffix = path.suffix.lower()
    codec, bits = probed if probed is not None else probe(path)
    deep = (bits or 16) > 16
    if suffix == ".m4a" and codec == "alac":
        return "m4a", ["-c:a", "alac"]
    if suffix == ".ogg" and codec == "opus":
        return "ogg", ["-c:a", "libopus", "-b:a", "256k"]
    if suffix in _LOSSY:
        ext, args = _LOSSY[suffix]
        return ext, list(args)
    if suffix == ".flac":
        return "flac", ["-c:a", "flac", "-sample_fmt", "s32" if deep else "s16"]
    if suffix == ".wav":
        return "wav", ["-c:a", "pcm_s24le" if deep else "pcm_s16le"]
    if suffix in (".aif", ".aiff"):
        return suffix[1:], ["-c:a", "pcm_s24be" if deep else "pcm_s16be"]
    return "flac", list(_FLAC24)  # webm and anything else: lossless


def _restore(svc, ctx, path: Path, out_wav: Path) -> float:
    restorer = get_restorer(svc)
    audio = load_audio(path)
    ctx.report("restoring", 0)
    t0 = time.perf_counter()

    def progress(f: float) -> None:
        if _chunk_delay():
            time.sleep(_chunk_delay())
        ctx.report("restoring", 85 * f)

    y = restorer.restore(audio, progress, lambda: ctx.cancelled)
    sf.write(out_wav, np.clip(y, -1.0, 1.0).T, SR, subtype="FLOAT")
    return (time.perf_counter() - t0) / max(audio.shape[1] / SR, 1e-6)


async def _encode(ctx, src_wav: Path, out: Path, args: list[str]) -> None:
    rate = 48000 if "libopus" in args else SR  # libopus only takes 48/24/16/12/8 kHz
    proc = await asyncio.create_subprocess_exec(
        find_tool("ffmpeg"), "-v", "error", "-nostdin", "-y", "-i", str(src_wav), "-ar", str(rate), "-ac", "2",
        *args, str(out), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    ctx.register_process(proc)
    _, err = await proc.communicate()
    ctx.check_cancelled()
    if proc.returncode != 0:
        stderr = err.decode("utf-8", "replace")
        log.warning("enhance encode failed: %s", stderr[-2000:])
        raise ffmpeg_error(stderr)


def _carry_tags(src: Path, dst: Path, bpm: float | None, key: str | None) -> None:
    try:
        if copy_tags(src, dst):
            return
        meta = read_tags(src)
        write_tags(dst, TrackMeta(meta.title, meta.artist, meta.album, meta.year, meta.source_url), read_cover(src))
        set_bpm_key(dst, bpm, key)
    except Exception as e:  # a format mutagen cannot tag: the audio still counts
        log.info("tags not copied to %s: %s", dst.name, e)


def _move_aside(original: Path, backup_dir: Path) -> Path:
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise user_error("disk")
    backup = unique_path(backup_dir, original.stem, original.suffix[1:])
    try:
        os.replace(original, backup)
        return backup
    except OSError as e:
        if getattr(e, "winerror", None) in (32, 33):  # sharing / lock violation: open in another program
            raise BUSY
        if isinstance(e, PermissionError) and getattr(e, "winerror", None) is None:
            raise BUSY
        if not (e.errno == errno.EXDEV or getattr(e, "winerror", None) == 17):
            raise user_error("disk")
    # another drive: copy the backup, then remove the original (a file in use stays where it was)
    try:
        shutil.copy2(original, backup)
    except OSError:
        backup.unlink(missing_ok=True)
        raise user_error("disk")
    try:
        original.unlink()
    except OSError:
        backup.unlink(missing_ok=True)
        raise BUSY
    return backup


def _remember_speed(svc, rtf: float) -> None:
    from ..settings import save_settings

    old = svc.settings.enhance_rtf
    svc.settings.enhance_rtf = round(rtf if old is None else 0.7 * old + 0.3 * rtf, 3)
    with contextlib.suppress(OSError):
        save_settings(svc.paths.settings_path, svc.settings)


def make_enhance_runner(svc, path: Path, mode: Mode, fmt: Fmt, then_stems=None, analyze_after: bool = False):
    path = Path(path)
    inner = _make_enhance(svc, path, mode, fmt, then_stems, analyze_after)

    async def run(ctx) -> dict:
        try:
            return await inner(ctx)
        except BaseException:
            # the enhance did not happen: what was asked after it still runs on the original
            if not ctx.finishing and path.is_file():
                from ..pipelines import submit_analysis, submit_stems

                if analyze_after and svc.analysis is not None:
                    submit_analysis(svc, path, path.stem)
                if then_stems is not None:
                    submit_stems(svc, path, then_stems.stems, then_stems.karaoke, path.stem)
            raise

    return run


def _make_enhance(svc, path: Path, mode: Mode, fmt: Fmt, then_stems, analyze_after: bool):
    async def run(ctx) -> dict:
        if not path.is_file():
            raise UserError("not_found", "No se encuentra el archivo")
        ext, args = await asyncio.to_thread(target_codec, path, fmt)
        ctx.report("loading_model", 0)
        restored = ctx.tmp_dir / "restored.wav"
        work = asyncio.ensure_future(asyncio.to_thread(_restore, svc, ctx, path, restored))
        try:
            rtf = await asyncio.shield(work)
        except asyncio.CancelledError:
            ctx.cancelled = True  # the thread stops at the next chunk; wait before tmp/ is removed
            with contextlib.suppress(BaseException):
                await work
            raise
        except JobCancelled:
            raise
        ctx.check_cancelled()
        ctx.report("encoding", 85)
        encoded = ctx.tmp_dir / f"out.{ext}"
        await _encode(ctx, restored, encoded, args)

        src_rec = svc.analysis.get(path)
        side = svc.analysis.read_sidecar(path) if src_rec else None
        track = svc.library.track_by_path(str(path))
        key = None
        if src_rec and src_rec.tonic and src_rec.mode:
            from ..analysis.camelot import tag_key

            key = tag_key(src_rec.tonic, src_rec.mode, svc.settings.key_notation)
        await asyncio.to_thread(_carry_tags, path, encoded, src_rec.bpm if src_rec else None, key)

        ctx.begin_finalize()
        ctx.report("saving", 95)
        backup = None
        if mode == "copy":
            final = unique_path(path.parent, enhanced_name(path.stem), ext)
            await asyncio.to_thread(_commit, encoded, final)
        else:
            final = path.with_suffix(f".{ext}")
            if final != path and final.exists():
                final = unique_path(path.parent, path.stem, ext)
            backup = await asyncio.to_thread(_move_aside, path, Path(svc.settings.music_dir) / "Originales")
            try:
                await asyncio.to_thread(_commit, encoded, final)
            except BaseException:
                with contextlib.suppress(OSError):
                    if not path.exists():  # put the original back (shutil.move also works across drives)
                        shutil.move(str(backup), str(path))
                raise

        # the file is in place: bookkeeping is best-effort, it never turns a done enhance into a failure
        try:
            _update_library(svc, track, path, final, mode, ext)
        except Exception as e:
            log.warning("library not updated after enhance of %s: %s", final.name, e)
        try:
            await asyncio.to_thread(_save_analysis, svc, src_rec, side, path, final, mode)
            if svc.analysis.get(final) is not None:
                _set_library_analysis(svc, final)
        except Exception as e:
            log.warning("analysis not carried over to %s: %s", final.name, e)
        _remember_speed(svc, rtf)
        title = track.title if track else path.stem
        svc.library.add_history(svc.library.video_source(track), title, track.artist if track else "",
                                "enhance", "done", track.id if track and mode == "replace" else None)
        if analyze_after and svc.analysis is not None:
            from ..pipelines import submit_analysis

            submit_analysis(svc, final, title)
        if then_stems is not None:
            from ..pipelines import submit_stems

            submit_stems(svc, final, then_stems.stems, then_stems.karaoke, title)
        return {"path": str(final), "moved_from": str(path) if final != path else None,
                "backup": str(backup) if backup else None}

    return run


def _save_analysis(svc, src_rec, side, path: Path, final: Path, mode: Mode) -> None:
    if src_rec is None:
        return
    from ..analysis.loudness import measure

    lufs, peak = measure(load_audio(final), SR)
    size, mtime = file_stamp(final)
    rec = replace(src_rec, path=str(final), size=size, mtime=mtime, lufs=lufs, peak_db=peak, created_at=now_iso())
    svc.analysis.save(rec, side or {})
    if mode == "replace" and final != path:
        svc.analysis.delete(path)


def _update_library(svc, track, path: Path, final: Path, mode: Mode, ext: str) -> None:
    if mode == "copy":
        title = enhanced_name(track.title) if track else final.stem
        svc.library.add_track(TrackRecord(
            None, None, title, track.artist if track else "", track.album if track else "",
            track.duration_s if track else None, None, str(final), ext, None, None, "",
            enhanced=True, origin_video_id=svc.library.video_source(track)))
    elif track is not None and final != path:
        svc.library.update_track_path(str(path), str(final), ext)
    elif track is None:
        svc.library.add_track(TrackRecord(None, None, final.stem, "", "", None, None, str(final), ext, None, None, ""))
    svc.library.set_enhanced(str(final))


def _set_library_analysis(svc, final: Path) -> None:
    from ..analysis.camelot import tag_key

    rec = svc.analysis.get(final)
    musical = tag_key(rec.tonic, rec.mode, "musical") if rec.tonic and rec.mode else None
    svc.library.set_track_analysis(str(final), rec.bpm, musical, rec.camelot, rec.lufs)


def submit_enhance(svc, path: Path, mode: Mode, fmt: Fmt, then_stems=None, analyze_after: bool = False):
    """Top-level job, one per file at a time (a second request for the same file returns the running one)."""
    from ..jobs import FINAL

    from ..server import _norm

    key = _norm(path)
    for j in svc.jobs.list():
        if j.type == "enhance" and j.status not in FINAL and _norm((j.payload or {}).get("path", "")) == key:
            return j
    title = f"Mejorar · {Path(path).stem}"
    return svc.jobs.submit("enhance", title, make_enhance_runner(svc, Path(path), mode, fmt, then_stems, analyze_after),
                           payload={"type": "enhance", "path": str(path), "mode": mode, "format": fmt})


PREVIEW_S = 15.0


def preview_start(sidecar: dict | None, duration: float) -> float:
    """Start of the first chorus/drop, else 30 % into the song; always leaves a full 15 s clip when possible."""
    start = next((float(s["start"]) for s in (sidecar or {}).get("sections") or [] if s.get("label") == "Estribillo/Drop"),
                 0.3 * duration)
    return round(max(0.0, min(start, duration - PREVIEW_S)), 3)


def _preview_work(svc, ctx, path: Path, folder: Path) -> tuple[Path, Path, float]:
    from ..server import _norm

    audio = load_audio(path)
    duration = audio.shape[1] / SR
    start = preview_start(svc.analysis.read_sidecar(path), duration)
    a = int(start * SR)
    clip = audio[:, a: a + int(PREVIEW_S * SR)]
    ctx.report("restoring", 0)
    y = get_restorer(svc).restore(clip, lambda f: ctx.report("restoring", 95 * f), lambda: ctx.cancelled)
    folder.mkdir(parents=True, exist_ok=True)
    orig, enh = folder / f"{ctx.job.id}-original.wav", folder / f"{ctx.job.id}-mejorado.wav"
    sf.write(orig, clip.T, SR, subtype="PCM_24")
    sf.write(enh, np.clip(y, -1.0, 1.0).T, SR, subtype="PCM_24")
    svc.allowed_paths.update({_norm(orig), _norm(enh)})
    return orig, enh, start


def make_preview_runner(svc, path: Path):
    """15 s of the original and of the restored audio, aligned, for the A/B check before saving."""
    path = Path(path)

    async def run(ctx) -> dict:
        if not path.is_file():
            raise UserError("not_found", "No se encuentra el archivo")
        ctx.report("loading_model", 0)
        work = asyncio.ensure_future(asyncio.to_thread(_preview_work, svc, ctx, path, svc.paths.tmp_dir / "preview"))
        try:
            orig, enh, start = await asyncio.shield(work)
        except asyncio.CancelledError:
            ctx.cancelled = True
            with contextlib.suppress(BaseException):
                await work
            raise
        return {"original": str(orig), "enhanced": str(enh), "start": start}

    return run
