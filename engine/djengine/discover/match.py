"""Find each imported song (Spotify / Apple Music) on YouTube Music: best candidate, status and alternatives."""
import asyncio
import logging
import re
from difflib import SequenceMatcher
from typing import Literal

from pydantic import BaseModel

from ..library import normalize_key
from ..search import SearchResult
from .links import ImportItem

log = logging.getLogger(__name__)
FOUND, REVIEW = 0.8, 0.5
CONCURRENCY = 4
_VERSIONS = ("remix", "live", "en vivo", "acoustic", "acustic", "sped up", "slowed", "instrumental", "karaoke", "cover")
_SPLIT_ARTISTS = re.compile(r"\s*(?:,|&|\by\b|\bx\b|\bfeat\.?|\bft\.?|\bwith\b)\s*", re.I)


class MatchResult(BaseModel):
    status: Literal["found", "review", "missing"]
    best: SearchResult | None = None
    alternatives: list[SearchResult] = []


def _title(s: str) -> str:
    return normalize_key("", s).split("|", 1)[1]


def _artist(s: str) -> str:
    return normalize_key(s, "").split("|", 1)[0]


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _title_score(item: ImportItem, cand: SearchResult) -> float:
    a, b = _title(item.title), _title(cand.title)
    r = _ratio(a, b)
    if any(w in b and w not in a for w in _VERSIONS):
        r *= 0.6  # a remix or live take must not win over the original the playlist asked for
    return r


def _artist_score(item: ImportItem, cand: SearchResult) -> float:
    theirs = _artist(cand.artist)
    names = [_artist(n) for n in _SPLIT_ARTISTS.split(item.artist or "") if n.strip()]
    if theirs and any(n and (n in theirs or theirs in n) for n in names):
        return 1.0
    return max([_ratio(n, theirs) for n in names] + [_ratio(_artist(item.artist), theirs)])


def _duration_score(item: ImportItem, cand: SearchResult) -> float:
    if not item.duration_s or not cand.duration_s:
        return 0.5
    diff = abs(item.duration_s - cand.duration_s)
    return 1.0 if diff <= 5 else 0.0 if diff > 15 else 1.0 - (diff - 5) / 10


def _far_duration(item: ImportItem, cand: SearchResult) -> bool:
    return bool(item.duration_s and cand.duration_s and abs(item.duration_s - cand.duration_s) > 15)


def score(item: ImportItem, cand: SearchResult) -> float:
    return 0.6 * _title_score(item, cand) + 0.3 * _artist_score(item, cand) + 0.1 * _duration_score(item, cand)


def match(search, item: ImportItem) -> MatchResult:
    try:
        cands = search.search(f"{item.artist} {item.title}".strip(), "songs")
    except Exception as e:
        log.info("match search failed for %s: %s", item.title, e)
        return MatchResult(status="missing")
    if not cands:
        return MatchResult(status="missing")
    ranked = sorted(cands, key=lambda c: score(item, c), reverse=True)
    best, top = ranked[0], score(item, ranked[0])
    alternatives = ranked[1:4]
    if top < REVIEW:
        return MatchResult(status="missing", best=None, alternatives=ranked[:3])
    # a known length off by more than 15 s is usually another version: someone should look at it
    status = "found" if top >= FOUND and not _far_duration(item, best) else "review"
    return MatchResult(status=status, best=best, alternatives=alternatives)


def make_match_runner(svc, items: list[ImportItem]):
    async def run(ctx) -> dict:
        sem = asyncio.Semaphore(CONCURRENCY)
        results: list[MatchResult | None] = [None] * len(items)
        done = 0

        async def one(i: int, item: ImportItem) -> None:
            nonlocal done
            async with sem:
                ctx.check_cancelled()
                r = await asyncio.to_thread(match, svc.search, item)
            results[i] = r
            done += 1
            ctx.report("matching", 100 * done / len(items))
            await svc.hub.broadcast({"type": "match.result", "job_id": ctx.job.id, "index": i,
                                     "result": r.model_dump()})

        await asyncio.gather(*(one(i, it) for i, it in enumerate(items)))
        return {"results": [r.model_dump() for r in results]}

    return run
