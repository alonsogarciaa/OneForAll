import asyncio
import contextlib
import uuid
import errno
import logging
import os
import shutil
from pathlib import Path

import mutagen
from pydantic import BaseModel, Field, field_validator

from .convert import ConvertOptions, convert_file, output_ext
from .errors import JobCancelled, UserError, user_error
from .jobs import FINAL, Job, JobContext, Runner
from .library import TrackRecord
from .naming import render_name, sanitize_filename, unique_path
from .search import SearchResult
from .tags import TrackMeta, square_cover, write_tags
from .download import fetch_thumbnail

log = logging.getLogger(__name__)


class ThenStems(BaseModel):
    stems: list[str] = Field(min_length=1)
    karaoke: bool = False

    @field_validator("stems")
    @classmethod
    def _known(cls, v):
        from .stems.names import STEMS

        bad = [s for s in v if s not in STEMS]
        if bad:
            raise ValueError(f"stem desconocido: {bad[0]}")
        return v


class DownloadRequest(BaseModel):
    target: SearchResult
    options: ConvertOptions
    force: bool = False
    skip_existing: bool = False
    then_stems: ThenStems | None = None


def _ensure_dir(d: Path) -> None:
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning("cannot create %s: %s", d, e)
        raise user_error("disk")


PART_PREFIX = "~oneforall-"


def sweep_parts(dirs) -> int:
    """Remove copies left half-written by a crash (only our own prefixed .part files)."""
    n = 0
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for f in d.rglob(f"{PART_PREFIX}*.part"):
            with contextlib.suppress(OSError):
                f.unlink()
                n += 1
    return n


def _commit(tmp_file: Path, final: Path) -> None:
    """Move a finished file into place. Never leaves a partial file under its final name."""
    try:
        os.replace(tmp_file, final)
        return
    except OSError as e:
        cross_device = e.errno == errno.EXDEV or getattr(e, "winerror", None) == 17
        if not cross_device:
            log.warning("cannot move into %s: %s", final, e)
            raise user_error("disk")
    part = final.with_name(f"{PART_PREFIX}{uuid.uuid4().hex}.part")  # swept at startup if we crash mid-copy
    try:
        shutil.copy2(tmp_file, part)
        os.replace(part, final)
    except OSError as e:
        part.unlink(missing_ok=True)
        log.warning("cannot copy into %s: %s", final, e)
        raise user_error("disk")


def _bitrate(opts: ConvertOptions) -> int | None:
    if opts.format == "mp3" and (opts.quality or "320").isdigit():
        return int(opts.quality or "320")
    return None


async def _cover(url: str | None) -> bytes | None:
    data = await asyncio.to_thread(fetch_thumbnail, url)
    if not data:
        return None
    try:
        return square_cover(data)
    except Exception as e:
        log.info("cover unusable (%s): %s", url, e)
        return None


def make_download_runner(svc, req: DownloadRequest, dest_dir: Path, playlist_id: int | None = None,
                         position: int | None = None) -> Runner:
    t = req.target

    async def run(ctx: JobContext) -> dict:
        if req.skip_existing:
            dup = svc.library.find_duplicate(t.id, t.artist, t.title)
            if dup is not None:
                return {"skipped": True, "existing_path": dup.path}
        try:
            src = await svc.downloader(ctx, t.url)
            ctx.check_cancelled()
            opts = req.options
            ext = output_ext(opts, src)
            if opts.format == "original":
                out = src
            else:
                out = ctx.tmp_dir / f"out.{ext}"
                await convert_file(ctx, src, out, opts, t.duration_s)

            ctx.report("tagging", 0)
            cover = await _cover(t.thumbnail)
            cover_path = None
            try:
                write_tags(out, TrackMeta(t.title, t.artist, t.album, "", t.url), cover)
            except Exception as e:  # e.g. webm kept as "original": mutagen cannot tag it
                log.info("tags not written for %s: %s", out.name, e)

            ctx.report("finalizing", 0)
            _ensure_dir(dest_dir)
            ctx.begin_finalize()
            name = render_name(svc.settings.name_template, {"artist": t.artist, "title": t.title, "album": t.album})
            final = unique_path(dest_dir, name, ext)
            await asyncio.to_thread(_commit, out, final)
        except (JobCancelled, asyncio.CancelledError):
            raise
        except UserError as e:
            svc.library.add_history(t.id, t.title, t.artist, "download", "failed")
            raise e

        track_id = svc.library.add_track(TrackRecord(
            id=None, video_id=t.id or None, title=t.title, artist=t.artist, album=t.album,
            duration_s=t.duration_s, views=t.views, path=str(final), format=req.options.format,
            bitrate=_bitrate(req.options), cover_path=cover_path, added_at="",
        ))
        svc.library.add_history(t.id, t.title, t.artist, "download", "done", track_id)
        st = svc.settings
        if st.analyze_on_download and svc.analysis is not None and not st.enhance_on_download:
            submit_analysis(svc, final, t.title)
        if st.enhance_on_download:
            from .enhance.runner import submit_enhance

            # analysis and stems start from the enhanced file, never while it is being rewritten
            submit_enhance(svc, final, st.enhance_mode, st.enhance_format, then_stems=req.then_stems,
                           analyze_after=st.analyze_on_download)
        elif req.then_stems is not None:
            submit_stems(svc, final, req.then_stems.stems, req.then_stems.karaoke, t.title)
        if playlist_id is not None:
            svc.library.add_playlist_track(playlist_id, track_id, position or 0)
        return {"path": str(final), "track_id": track_id}

    return run


async def start_playlist(svc, playlist_id: str, options: ConvertOptions) -> Job:
    info = await asyncio.to_thread(svc.search.get_playlist, playlist_id)
    seen: set[str] = set()
    info.tracks = [t for t in info.tracks if not (t.id in seen or seen.add(t.id))]  # same video twice: one download
    return _submit_playlist(svc, info.title, info.id, info.tracks, options,
                            {"type": "playlist", "id": playlist_id, "options": options.model_dump()})


def start_import(svc, name: str, targets: list[SearchResult], options: ConvertOptions) -> Job:
    """A list read from Spotify / Apple Music / SoundCloud, already matched: same flow as a YouTube playlist."""
    seen: set[str] = set()
    targets = [t for t in targets if not (t.id in seen or seen.add(t.id))]
    return _submit_playlist(svc, name, None, targets, options,
                            {"type": "import", "name": name, "options": options.model_dump()})


def _submit_playlist(svc, title: str, yt_id: str | None, tracks: list[SearchResult], options: ConvertOptions,
                     payload: dict) -> Job:
    folder = Path(svc.settings.music_dir) / (sanitize_filename(title) or "Playlist")

    async def parent(ctx: JobContext) -> dict:
        _ensure_dir(folder)
        pl_db = svc.library.add_playlist(yt_id, title, str(folder))
        kids = []
        for i, t in enumerate(tracks):
            req = DownloadRequest(target=t, options=options, skip_existing=True)
            kids.append(svc.jobs.submit(
                "download", t.title, make_download_runner(svc, req, folder, pl_db, i),
                parent_id=ctx.job.id,
                payload={"request": req.model_dump(), "dest_dir": str(folder), "playlist_id": pl_db, "position": i},
            ))
        total = len(kids) or 1
        while True:
            finished = [svc.jobs.get(k.id) for k in kids if svc.jobs.get(k.id).status in FINAL]
            ctx.report("downloading", len(finished) / total * 100)
            if len(finished) == len(kids):
                break
            await asyncio.sleep(0.2)
        result = {"done": 0, "skipped": 0, "failed": [], "cancelled": 0, "options": options.model_dump()}
        for i, (k, track) in enumerate(zip(kids, tracks)):
            j = svc.jobs.get(k.id)
            if j.status == "done" and (j.result or {}).get("skipped"):
                result["skipped"] += 1
            elif j.status == "done":
                result["done"] += 1
            elif j.status == "failed":
                result["failed"].append({"title": j.title, "child_id": j.id, "target": track.model_dump(),
                                         "dest_dir": str(folder), "playlist_id": pl_db, "position": i, **(j.error or {})})
            else:
                result["cancelled"] += 1
        return result

    return svc.jobs.submit("playlist", title, parent, payload=payload)


def submit_analysis(svc, path: Path, title: str | None = None, force: bool = False, reset_bpm: bool = False):
    """Top-level analysis job: never a child, so it cannot delay or fail a download or playlist."""
    from .analysis.runner import make_analysis_runner
    from .jobs import FINAL

    # one analysis per file at a time: two concurrent runs would each rewrite the tags and stale the other's cache
    for j in svc.jobs.list():
        if j.type == "analysis" and j.status not in FINAL and (j.payload or {}).get("paths") == [str(path)]:
            return j
    return svc.jobs.submit(
        "analysis", title or Path(path).stem, make_analysis_runner(svc, Path(path), force=force, reset_bpm=reset_bpm),
        payload={"type": "analysis", "paths": [str(path)], "force": force, "reset_bpm": reset_bpm},
    )


def submit_stems(svc, path: Path, stems: list[str], karaoke: bool = False, title: str | None = None):
    """Top-level stems job (never a child): a failed separation cannot fail the download."""
    from .stems.runner import make_stems_runner

    return svc.jobs.submit(
        "stems", title or Path(path).stem, make_stems_runner(svc, Path(path), list(stems), karaoke),
        payload={"type": "stems", "paths": [str(path)], "stems": list(stems), "karaoke": karaoke},
    )


def make_convert_runner(svc, src: Path, options: ConvertOptions) -> Runner:
    src = Path(src)

    async def run(ctx: JobContext) -> dict:
        if not src.is_file():
            svc.library.add_history(None, src.stem, "", "convert", "failed")
            raise UserError("internal", "No se encuentra el archivo")
        ext = output_ext(options, src)
        tmp_out = ctx.tmp_dir / f"out.{ext}"
        try:
            info = mutagen.File(src)
            duration = info.info.length if info is not None else None
        except Exception:
            duration = None
        try:
            await convert_file(ctx, src, tmp_out, options, duration)
            ctx.report("finalizing", 0)
            ctx.begin_finalize()
            final = unique_path(src.parent, src.stem, ext)
            await asyncio.to_thread(_commit, tmp_out, final)
        except (JobCancelled, asyncio.CancelledError):
            raise
        except UserError:
            svc.library.add_history(None, src.stem, "", "convert", "failed")
            raise
        svc.library.add_history(None, src.stem, "", "convert", "done")
        return {"path": str(final)}

    return run
