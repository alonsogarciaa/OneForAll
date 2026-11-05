import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, model_validator

from .errors import UserError, user_error
from .tools import find_tool

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FormatSpec:
    ext: str
    lossless: bool


FORMATS: dict[str, FormatSpec] = {
    "mp3": FormatSpec("mp3", False),
    "aac": FormatSpec("m4a", False),
    "alac": FormatSpec("m4a", True),
    "opus": FormatSpec("opus", False),
    "ogg": FormatSpec("ogg", False),
    "flac": FormatSpec("flac", True),
    "wav": FormatSpec("wav", True),
    "aiff": FormatSpec("aiff", True),
    "original": FormatSpec("", False),  # ext comes from the source file
}
MP3_QUALITIES = {"128", "192", "256", "320", "v0"}
SAMPLE_RATES = {44100, 48000, 96000}
BIT_DEPTHS = {16, 24}


class ConvertOptions(BaseModel):
    format: str
    quality: str | None = None
    sample_rate: int | None = None
    bit_depth: int | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.format not in FORMATS:
            raise ValueError(f"formato desconocido: {self.format}")
        if self.format == "mp3" and self.quality is not None and self.quality not in MP3_QUALITIES:
            raise ValueError(f"calidad MP3 no válida: {self.quality}")
        lossless = FORMATS[self.format].lossless
        if (self.sample_rate is not None or self.bit_depth is not None) and not lossless:
            raise ValueError("frecuencia y profundidad solo para formatos sin pérdida")
        if self.sample_rate is not None and self.sample_rate not in SAMPLE_RATES:
            raise ValueError(f"frecuencia no válida: {self.sample_rate}")
        if self.bit_depth is not None and self.bit_depth not in BIT_DEPTHS:
            raise ValueError(f"profundidad no válida: {self.bit_depth}")
        return self


def output_ext(opts: ConvertOptions, src: Path) -> str:
    return FORMATS[opts.format].ext or src.suffix.lstrip(".")


def _codec_args(opts: ConvertOptions) -> list[str]:
    deep = opts.bit_depth == 24
    match opts.format:
        case "mp3":
            q = opts.quality or "320"
            return ["-c:a", "libmp3lame", "-q:a", "0"] if q == "v0" else ["-c:a", "libmp3lame", "-b:a", f"{q}k"]
        case "aac":
            return ["-c:a", "aac", "-b:a", "256k"]
        case "alac":
            return ["-c:a", "alac", "-sample_fmt", "s32p" if deep else "s16p"]
        case "opus":
            return ["-c:a", "libopus", "-b:a", "160k"]
        case "ogg":
            return ["-c:a", "libvorbis", "-q:a", "6"]
        case "flac":
            return ["-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24"] if deep else ["-c:a", "flac", "-sample_fmt", "s16"]
        case "wav":
            return ["-c:a", "pcm_s24le" if deep else "pcm_s16le"]
        case "aiff":
            return ["-c:a", "pcm_s24be" if deep else "pcm_s16be"]
        case "original":
            return ["-c:a", "copy"]
    raise ValueError(opts.format)


def build_ffmpeg_args(src: Path, dst: Path, opts: ConvertOptions) -> list[str]:
    args = ["-hide_banner", "-nostdin", "-i", str(src), "-vn", "-map_metadata", "0", *_codec_args(opts)]
    if opts.sample_rate:
        args += ["-ar", str(opts.sample_rate)]
    return args + ["-y", "-progress", "pipe:1", "-nostats", str(dst)]


def ffmpeg_error(stderr: str) -> UserError:
    if "No space left" in stderr or "There is not enough space" in stderr:
        return user_error("disk")
    return UserError("internal", "No se pudo convertir el archivo")


async def convert_file(ctx, src: Path, dst: Path, opts: ConvertOptions, duration_s: float | None) -> Path:
    proc = await asyncio.create_subprocess_exec(
        find_tool("ffmpeg"),
        *build_ffmpeg_args(Path(src), Path(dst), opts),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    ctx.register_process(proc)
    ctx.report("converting", 0)
    stderr_task = asyncio.create_task(proc.stderr.read())
    async for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("out_time_us=") and duration_s:
            try:
                done_s = int(line.split("=", 1)[1]) / 1_000_000
            except ValueError:
                continue
            ctx.report("converting", min(99.0, done_s / duration_s * 100))
    await proc.wait()
    stderr = (await stderr_task).decode("utf-8", "replace")
    ctx.check_cancelled()
    if proc.returncode != 0:
        log.warning("ffmpeg failed (%s): %s", proc.returncode, stderr[-2000:])
        Path(dst).unlink(missing_ok=True)
        raise ffmpeg_error(stderr)
    ctx.report("converting", 100)
    return Path(dst)
