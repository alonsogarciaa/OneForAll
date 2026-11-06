"""ffmpeg filter graph for exporting a mix: stretch/pitch per stem (rubberband), sum, limiter."""
from pathlib import Path
from typing import Literal

from ..errors import UserError
from .state import MixState, StemState, audible, effective_semis

Range = Literal["full", "loop"]


def build_mix_graph(stems: dict[str, Path], state: MixState, rng: Range) -> tuple[list[str], str]:
    """(ffmpeg input args, filter_complex ending in [out]). Paths only ever go in -i arguments."""
    if rng == "loop" and state.loop is None:
        raise UserError("bad_request", "No hay bucle")
    names = audible(state, list(stems))
    if not names:
        raise UserError("bad_request", "No hay ningún stem audible")
    inputs: list[str] = []
    chains: list[str] = []
    for i, name in enumerate(names):
        inputs += ["-i", str(stems[name])]
        parts = []
        if rng == "loop":
            parts += [f"atrim=start={state.loop.start:.3f}:end={state.loop.end:.3f}", "asetpts=N/SR/TB"]
        pitch = 2 ** (effective_semis(state, name) / 12)
        if state.rate != 1.0 or effective_semis(state, name) != 0:
            parts.append(f"rubberband=tempo={state.rate:.2f}:pitch={pitch:.6f}:pitchq=quality:transients=mixed")
        parts.append(f"volume={state.stems.get(name, StemState()).gain:.3f}")
        chains.append(f"[{i}:a]{','.join(parts)}[s{i}]")
    labels = "".join(f"[s{i}]" for i in range(len(names)))
    chains.append(f"{labels}amix=inputs={len(names)}:normalize=0:duration=longest,"
                  f"volume={state.master:.3f},alimiter=limit=0.99:level=false[out]")
    return inputs, ";".join(chains)


def output_seconds(state: MixState, duration: float, rng: Range) -> float:
    if rng == "loop" and state.loop:
        end = min(state.loop.end, duration) if duration else state.loop.end  # ffmpeg stops at the end of the audio
        span = max(0.0, end - state.loop.start)
    else:
        span = duration
    return span / state.rate


def _mmss(t: float) -> str:
    t = int(round(t))
    return f"{t // 60:02d}m{t % 60:02d}s"


def export_name(state: MixState, rng: Range, ext: str) -> str:
    tags = []
    if state.rate != 1.0:
        tags.append(f"{state.rate:.2f}x")
    if state.semis:
        tags.append(f"{state.semis:+d}")
    suffix = f" ({', '.join(tags)})" if tags else ""
    base = f"loop {_mmss(state.loop.start)}-{_mmss(state.loop.end)}" if rng == "loop" and state.loop else "mix"
    return f"{base}{suffix}.{ext}"
