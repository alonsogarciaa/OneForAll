"""Recommendations: the seed song of a library track, and rows enriched with the quick analysis cache."""
import logging

from ..search import SearchResult

log = logging.getLogger(__name__)


def seed_for_track(svc, track) -> str | None:
    """The track's YouTube video, its original's (copies), or the first YouTube Music match of "artist title"."""
    vid = svc.library.video_source(track)
    if vid and not vid.startswith("sc:"):
        return vid
    try:
        hits = svc.search.search(f"{track.artist} {track.title}".strip(), "songs")
    except Exception as e:
        log.info("seed search failed for %s: %s", track.title, e)
        return None
    return hits[0].id if hits else None


def known_analysis(svc, video_ids: list[str]) -> dict[str, dict]:
    """BPM and key already known for these videos (quick cache or a library track); filled in by the quick analysis."""
    from .quick import lookup

    return lookup(svc, video_ids)


def rec_rows(svc, items: list[SearchResult]) -> list[dict]:
    known = known_analysis(svc, [i.id for i in items])
    rows = []
    for it in items:
        it.in_library = svc.library.find_duplicate(it.id, it.artist, it.title) is not None
        k = known.get(it.id)
        rows.append({**it.model_dump(), "bpm": k.get("bpm") if k else None, "camelot": k.get("camelot") if k else None,
                     "analysed": k is not None})
    return rows
