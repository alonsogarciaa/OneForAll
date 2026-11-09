"""video_export job: an MP4 per track with the original YouTube video, or the cover when there is none."""
import asyncio
import logging
import shutil
from pathlib import Path

from ..errors import JobCancelled, UserError
from ..naming import sanitize_filename, unique_path
from ..stems.runner import _duration
from ..tags import read_cover
from ..tools import find_tool

log = logging.getLogger(__name__)
_SIZE = {"720": (1280, 720), "1080": (1920, 1080), "max": (1920, 1080)}
BG = "0x111114"
NO_VIDEO = "Sin vídeo original"
FAILED = "No se pudo crear el vídeo"
_FONT = Path("C:/Windows/Fonts/segoeui.ttf")


def _ff_path(p: Path) -> str:
    """A path inside a filter argument: forward slashes, escaped drive colon, quoted."""
    return "'" + str(p).replace("\\", "/").replace(":", "\\:") + "'"


def video_args(audio: Path, image: Path | None, still: bool, quality: str, speed: float, out: Path,
               text_file: Path | None = None, duration: float | None = None) -> list[str]:
    """ffmpeg arguments after the executable. image None + still: a dark card with the text of text_file."""
    w, h = _SIZE.get(quality, _SIZE["1080"])
    if still and image is not None:
        inputs = ["-loop", "1", "-framerate", "2", "-i", str(image)]
        vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={BG},format=yuv420p"
    elif still:
        inputs = ["-f", "lavfi", "-i", f"color=c={BG}:s={w}x{h}:r=2"]
        font = f"fontfile={_ff_path(_FONT)}:" if _FONT.is_file() else ""
        vf = (f"drawtext={font}textfile={text_file.name}:expansion=none:fontcolor=white:fontsize={h // 18}:"
              f"x=(w-text_w)/2:y=(h-text_h)/2:line_spacing={h // 40},format=yuv420p") if text_file else "format=yuv420p"
    else:
        inputs = ["-i", str(image)]
        vf = (f"setpts=PTS*{1 / speed:.6f}," if abs(speed - 1) > 1e-6 else "") + "tpad=stop_mode=clone:stop_duration=36000"
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
    if still:
        enc += ["-tune", "stillimage"]
    return ["-v", "error", "-nostdin", "-y", *inputs, "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-vf", vf,
            *enc, "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", "-shortest",
            *(["-t", f"{duration:.3f}"] if duration else []),  # an endless still image would ignore -shortest
            "-progress", "pipe:1", "-nostats", str(out)]


def _cover_jpeg(data: bytes, out: Path) -> Path | None:
    """Re-encode the cover; an unreadable one returns None (ffmpeg -loop would spin forever on it)."""
    import io

    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as im:
            im.convert("RGB").save(out, "JPEG", quality=92)
        return out
    except Exception as e:
        log.info("cover unreadable, using the title card: %s", e)
        return None


def videos_dir(svc, out_dir: str | None) -> Path:
    return Path(out_dir or svc.settings.videos_dir or Path(svc.settings.music_dir) / "Videos")


def _speed(svc, path: Path) -> float:
    """A retempo copy plays its original's video at copy BPM / original BPM."""
    side = svc.analysis.read_sidecar(path) or {}
    origin = side.get("origin_bpm")
    bpm = (side.get("grid") or {}).get("bpm")
    if not bpm:
        rec = svc.analysis.get_any(path)
        bpm = rec.bpm if rec else None
    return float(bpm) / float(origin) if origin and bpm else 1.0


async def _fetch(svc, ctx, vid: str, quality: str, cache: Path) -> Path:
    hit = next(iter(sorted(cache.glob(f"{vid}-{quality}.*"))), None)
    if hit is not None:
        return hit
    got = await svc.video_downloader(ctx, f"https://www.youtube.com/watch?v={vid}", quality)
    cache.mkdir(parents=True, exist_ok=True)
    from ..pipelines import _commit

    final = cache / f"{vid}-{quality}{got.suffix}"
    await asyncio.to_thread(_commit, got, final)
    return final


async def _render(ctx, args: list[str], total: float, base: float, share: float, cwd: Path | None = None) -> None:
    proc = await asyncio.create_subprocess_exec(find_tool("ffmpeg"), *args, cwd=str(cwd) if cwd else None,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    ctx.register_process(proc)
    err_task = asyncio.create_task(proc.stderr.read())
    async for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("out_time_us=") and total:
            try:
                ctx.report("rendering", base + share * min(1.0, int(line.split("=", 1)[1]) / 1e6 / total))
            except ValueError:
                continue
    await proc.wait()
    stderr = (await err_task).decode("utf-8", "replace")
    ctx.check_cancelled()
    if proc.returncode != 0:
        log.warning("video render failed (%s): %s", proc.returncode, stderr[-2000:])
        raise UserError("render_failed", FAILED)


def make_video_export_runner(svc, track_ids: list[int], quality: str, out_dir: str | None):
    async def run(ctx) -> dict:
        wanted = list(dict.fromkeys(track_ids))
        by_id = {t.id: t for t in svc.library.list_tracks() if t.id in set(wanted)}
        dest = videos_dir(svc, out_dir)
        result = {"exported": [], "fallbacks": [], "failed": []}
        n = max(1, len(wanted))
        for i, tid in enumerate(wanted):
            t = by_id.get(tid)
            base, share = 100 * i / n, 100 / n
            if t is None or not Path(t.path).is_file():
                result["failed"].append({"title": t.title if t else str(tid), "reason": "Archivo no encontrado"})
                continue
            path = Path(t.path)
            work = ctx.tmp_dir / f"t{i}"
            work.mkdir()
            ctx.report("fetching_video", base)
            vid = svc.library.video_source(t)
            image, still, reason = None, True, NO_VIDEO
            if vid:
                try:
                    image, still, reason = await _fetch(svc, ctx, vid, quality, dest / ".cache"), False, None
                except (JobCancelled, asyncio.CancelledError):
                    raise
                except UserError as e:
                    reason = e.message
            text_file = None
            if still:
                result["fallbacks"].append({"title": t.title, "reason": reason})
                try:
                    cover = read_cover(path)
                except Exception:
                    cover = None
                image = _cover_jpeg(cover, work / "cover.jpg") if cover else None
                if image is None:
                    text_file = work / "title.txt"
                    text_file.write_text("\n".join(x for x in (t.artist, t.title) if x), encoding="utf-8")
            speed = 1.0 if still else _speed(svc, path)
            tmp_out = work / "out.mp4"
            seconds = _duration(path)
            args = video_args(path, image, still, quality, speed, tmp_out, text_file=text_file, duration=seconds)
            try:
                await _render(ctx, args, seconds or 0.0, base, share * 0.95, cwd=work)  # textfile is relative
            except UserError:
                result["failed"].append({"title": t.title, "reason": FAILED})
                continue
            ctx.report("saving", base + share * 0.97)
            try:
                dest.mkdir(parents=True, exist_ok=True)
            except OSError:
                from ..errors import user_error

                raise user_error("disk")
            name = sanitize_filename(f"{t.artist} - {t.title}" if t.artist else t.title) or path.stem
            final = unique_path(dest, name, "mp4")
            from ..pipelines import _commit

            await asyncio.to_thread(_commit, tmp_out, final)
            shutil.rmtree(work, ignore_errors=True)
            result["exported"].append({"title": t.title, "file": str(final)})
        return result

    return run
