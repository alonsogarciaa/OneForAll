import asyncio
import logging
from pathlib import Path

import librosa
import numpy as np

from ..errors import UserError
from ..tags import set_bpm_key
from .audio_io import decode
from .camelot import display_key, tag_key
from .config import ANALYSIS_VERSION, DEFAULT_KEY_METHOD, DEFAULT_TEMPO_METHOD
from .key import estimate_key
from .loudness import measure
from .store import AnalysisRecord, file_stamp, now_iso
from .tempo import estimate_tempo
from .waveform import compute

log = logging.getLogger(__name__)
SR = 22050
SR_FULL = 44100

for _optional in ("djengine.analysis.tempo_deeprhythm", "djengine.analysis.key_cnn"):
    try:  # registers deeprhythm / cnn when their dependencies exist; otherwise estimators fall back
        __import__(_optional)
    except ImportError as e:
        log.warning("optional analysis method not available: %s", e)


def _finite(x):
    return None if x is None or not np.isfinite(x) else float(x)


def result_dict(rec: AnalysisRecord) -> dict:
    return {
        "path": rec.path, "bpm": rec.bpm, "camelot": rec.camelot, "lufs": rec.lufs,
        "display_key": display_key(rec.tonic, rec.mode) if rec.tonic and rec.mode else None,
    }


def _analyse(path: Path, ctx, bpm_lo: int, bpm_hi: int):
    """Blocking work, run in a thread: one decode, then every estimator."""
    ctx.report("decoding", 0)
    stereo = decode(path, sr=SR_FULL, mono=False)
    mono44 = stereo.mean(axis=0).astype(np.float32)
    y = librosa.resample(mono44, orig_sr=SR_FULL, target_sr=SR) if mono44.size else mono44
    ctx.check_cancelled()
    ctx.report("tempo", 15)
    tempo = estimate_tempo(y, SR, method=DEFAULT_TEMPO_METHOD, lo=bpm_lo, hi=bpm_hi)
    ctx.check_cancelled()
    ctx.report("key", 40)
    key = estimate_key(mono44, SR_FULL, method=DEFAULT_KEY_METHOD)
    ctx.check_cancelled()
    ctx.report("loudness", 70)
    lufs, peak = measure(stereo, SR_FULL)
    ctx.check_cancelled()
    ctx.report("waveform", 85)
    wf = compute(y, SR)
    ctx.check_cancelled()
    return tempo, key, lufs, peak, wf, len(y) / SR


def make_analysis_runner(svc, path: Path, force: bool = False, reset_bpm: bool = False):
    path = Path(path)

    async def run(ctx) -> dict:
        if not path.is_file():
            raise UserError("unreadable", "No se puede leer el audio de este archivo")
        store = svc.analysis
        cached = store.get(path)
        if cached and cached.version == ANALYSIS_VERSION and not force and not reset_bpm:
            return result_dict(cached)
        previous = store.get_any(path)
        s = svc.settings
        tempo, key, lufs, peak, wf, duration = await asyncio.to_thread(_analyse, path, ctx, s.bpm_min, s.bpm_max)

        ctx.begin_finalize()
        ctx.report("saving", 95)
        bpm, source = (tempo.bpm or None), "auto"
        if previous and previous.bpm_source == "manual" and not reset_bpm:
            bpm, source = previous.bpm, "manual"
        size, mtime = file_stamp(path)
        rec = AnalysisRecord(
            path=str(path), size=size, mtime=mtime, bpm=_finite(bpm), bpm_confidence=_finite(tempo.confidence),
            bpm_source=source, tonic=key.tonic, mode=key.mode, camelot=key.camelot,
            key_confidence=_finite(key.confidence), lufs=_finite(lufs), peak_db=_finite(peak),
            version=ANALYSIS_VERSION, created_at=now_iso(),
        )
        store.save(rec, {"beats": tempo.beats, "waveform": wf, "duration": round(duration, 3)})
        has_key = bool(key.tonic and key.mode)  # silence: no key is stored or written
        before = file_stamp(path)
        if write_analysis_tags(path, rec.bpm, tag_key(key.tonic, key.mode, s.key_notation) if has_key else None):
            store.restamp(path)  # our own tag write must not invalidate the caches
            if getattr(svc, "stems", None) is not None:
                svc.stems.restamp(path, before)
        musical = tag_key(key.tonic, key.mode, "musical") if has_key else None
        svc.library.set_track_analysis(str(path), rec.bpm, musical, rec.camelot, rec.lufs)
        return result_dict(rec)

    return run


def write_analysis_tags(path: Path, bpm: float | None, key_tag: str | None) -> bool:
    """Write only BPM/key into the file. False if the format cannot be tagged."""
    try:
        set_bpm_key(path, bpm, key_tag)
        return True
    except Exception as e:  # unsupported container or locked file: the analysis still counts
        log.info("analysis tags not written for %s: %s", Path(path).name, e)
        return False
