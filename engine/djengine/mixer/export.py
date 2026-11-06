"""mix_export job: render the current mix (or its loop) from the stems at maximum quality."""
import asyncio
import logging
from pathlib import Path

from ..convert import ffmpeg_error
from ..errors import UserError
from ..naming import unique_path
from ..stems.names import ext_for
from ..stems.runner import _duration
from ..tools import find_tool
from .graph import Range, build_mix_graph, export_name, output_seconds
from .state import MixState

log = logging.getLogger(__name__)
MIXER_MAX_SECONDS = 12 * 60
_CODEC = {
    "wav16": ["-c:a", "pcm_s16le"],
    "wav24": ["-c:a", "pcm_s24le"],
    "flac": ["-c:a", "flac"],
    "mp3": ["-c:a", "libmp3lame", "-b:a", "320k"],
}


def _extra_args() -> list[str]:
    return []  # seam for tests (slow renders)


def mixer_stems(got: dict[str, Path]) -> dict[str, Path]:
    """Lead + backing vocals replace vocals, so the voice is not heard twice."""
    if "lead_vocals" in got and "backing_vocals" in got:
        return {k: v for k, v in got.items() if k != "vocals"}
    return dict(got)


def _title(svc, path: Path) -> str:
    t = svc.library.track_by_path(str(path))
    return t.title if t else path.stem


def make_mix_export_runner(svc, path: Path, state: MixState, rng: Range, fmt: str | None):
    path = Path(path)

    async def run(ctx) -> dict:
        try:
            return await _export(ctx)
        except UserError:
            svc.library.add_history(None, _title(svc, path), "", "export", "failed")
            raise

    async def _export(ctx) -> dict:
        stems = mixer_stems(svc.stems.get(path))
        if not stems or not all(p.is_file() for p in stems.values()):
            raise UserError("no_stems", "Faltan stems de esta canción")
        lengths = [d for d in (_duration(p) for p in stems.values()) if d is not None]
        seconds = max(lengths) if lengths else None  # the export lasts as long as the longest stem
        if seconds is not None and seconds > MIXER_MAX_SECONDS:
            raise UserError("too_long", "Pista demasiado larga para el mezclador")
        if rng == "loop" and state.loop and seconds is not None and state.loop.start >= seconds:
            raise UserError("bad_request", "El bucle empieza después del final de la canción")
        inputs, fc = build_mix_graph(stems, state, rng)
        f = fmt or svc.settings.stems_format
        ext = ext_for(f)
        tmp = ctx.tmp_dir / f"mix.{ext}"
        total = output_seconds(state, seconds or 0.0, rng)
        ctx.report("rendering", 0)
        proc = await asyncio.create_subprocess_exec(
            find_tool("ffmpeg"), "-v", "error", "-nostdin", "-y", *_extra_args(), *inputs,
            "-filter_complex", fc, "-map", "[out]", "-ar", "44100", "-ac", "2", *_CODEC[f],
            "-progress", "pipe:1", "-nostats", str(tmp),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        ctx.register_process(proc)
        err_task = asyncio.create_task(proc.stderr.read())
        async for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("out_time_us=") and total:
                try:
                    done_s = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                ctx.report("rendering", min(99.0, done_s / total * 100))
        await proc.wait()
        stderr = (await err_task).decode("utf-8", "replace")
        ctx.check_cancelled()
        if proc.returncode != 0:
            log.warning("mix export failed (%s): %s", proc.returncode, stderr[-2000:])
            raise ffmpeg_error(stderr)

        ctx.begin_finalize()
        ctx.report("saving", 99)
        from ..pipelines import _commit

        folder = next(iter(stems.values())).parent
        name = export_name(state, rng, ext)
        final = unique_path(folder, name[: -(len(ext) + 1)], ext)
        await asyncio.to_thread(_commit, tmp, final)
        svc.mixer.add_export(path, final)
        svc.library.add_history(None, _title(svc, path), "", "export", "done")
        return {"file": str(final)}

    return run
