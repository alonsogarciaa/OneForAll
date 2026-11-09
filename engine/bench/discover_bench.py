"""Phase 5a bench: Spotify matching hit rate and recommendations with BPM/key, against the real services.

Usage: python -m bench.discover_bench
Prints a Markdown summary; the found matches are listed so a person can check them by hand.
"""
import asyncio
import tempfile
import time
from pathlib import Path

from djengine.discover.links import parse_link, read_link
from djengine.discover.match import match
from djengine.discover.quick import CLIP_S, START_AT, download_clip, quick_analyse
from djengine.search import SearchService

PLAYLISTS = [
    "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",  # Today's Top Hits
    "https://open.spotify.com/playlist/37i9dQZEVXbNFJfN1Vw8d9",  # Top 50 España
    "https://open.spotify.com/playlist/37i9dQZF1DX10zKzsJ2jva",  # Viva Latino
]
CONC = 4
SEEDS = ["Kev3r6W4TPo", "n5ZZnwDhuow", "TNb6aBmx3O8"]  # LA GRACIOSA, CONTIGO, BUENAS NOCHES


class Ctx:
    def __init__(self, d: Path):
        self.tmp_dir = d
        self.cancelled = False

    def register_process(self, proc):
        pass

    def check_cancelled(self):
        pass

    def report(self, *a, **k):
        pass


def bench_matching(search: SearchService) -> None:
    print("## Emparejado de Spotify\n")
    print("| Playlist | Canciones | found | review | missing | % found |")
    print("|---|---|---|---|---|---|")
    samples = []
    for url in PLAYLISTS:
        lst = read_link(parse_link(url))
        res = [match(search, it) for it in lst.items]
        n = len(res)
        f = sum(r.status == "found" for r in res)
        rv = sum(r.status == "review" for r in res)
        print(f"| {lst.name} | {n} | {f} | {rv} | {n - f - rv} | {100 * f / n:.0f} % |")
        samples += [(it, r.best) for it, r in zip(lst.items, res) if r.status == "found"][:10]
    print("\n### Muestra de `found` para revisar a mano\n")
    for it, best in samples:
        print(f"- {it.artist} — {it.title} → {best.artist} — {best.title} ({best.id})")


async def bench_recs(search: SearchService) -> None:
    print("\n## Recomendaciones con BPM y tonalidad\n")
    print("| Semilla | Recomendaciones | Con datos | Tiempo para el 80 % |")
    print("|---|---|---|---|")
    for seed in SEEDS:
        recs = search.similar(seed)
        sem = asyncio.Semaphore(CONC)
        t0 = time.perf_counter()
        times: list[float] = []

        async def one(r):
            async with sem:
                with tempfile.TemporaryDirectory() as d:
                    ctx = Ctx(Path(d))
                    try:
                        clip = await download_clip(ctx, r.url, (r.duration_s or 200) * START_AT, CLIP_S)
                        res = await asyncio.to_thread(quick_analyse, clip, 70, 180)
                        if res.get("bpm"):
                            times.append(time.perf_counter() - t0)
                    except Exception as e:
                        print(f"<!-- {r.id}: {e} -->")

        await asyncio.gather(*(one(r) for r in recs))
        times.sort()
        need = max(1, int(0.8 * len(recs)))
        t80 = f"{times[need - 1]:.0f} s" if len(times) >= need else "no llega"
        print(f"| {seed} | {len(recs)} | {len(times)} | {t80} |")


def main() -> None:
    search = SearchService()
    bench_matching(search)
    asyncio.run(bench_recs(search))


if __name__ == "__main__":
    main()
