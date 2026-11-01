"""Run every tempo/key candidate over the GiantSteps index and write the report.

usage: python -m bench.run --tempo librosa,deeprhythm --key edma,temperley,krumhansl,cnn [--limit N]
"""
import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from bench.metrics import accuracy1, accuracy2, mirex_score

HERE = Path(__file__).resolve().parent
INDEX = HERE / "data" / "index.json"
RESULTS = HERE / "results.json"
REPORT = HERE.parents[1] / "docs" / "bench" / "2026-11-fase2.md"
SR = 22050
os.environ.setdefault("ONEFORALL_TOOLS", str(HERE.parents[1] / "build" / "runtime" / "bin"))


def _analyze(item: dict, tempo_methods: list[str], key_methods: list[str]) -> dict:
    for optional in ("djengine.analysis.tempo_deeprhythm", "djengine.analysis.key_cnn"):
        try:
            __import__(optional)  # registers extra methods when their dependencies are installed
        except ImportError:
            pass
    from djengine.analysis.audio_io import decode
    from djengine.analysis.key import estimate_key
    from djengine.analysis.tempo import estimate_tempo

    y = decode(Path(item["audio"]), sr=SR)
    out = {"id": item["id"], "tempo": {}, "key": {}, "secs": {}}
    for m in tempo_methods:
        t0 = time.perf_counter()
        out["tempo"][m] = estimate_tempo(y, SR, method=m).bpm
        out["secs"][f"tempo:{m}"] = time.perf_counter() - t0
    y44 = decode(Path(item["audio"]), sr=44100) if "cnn" in key_methods else None
    for m in key_methods:
        t0 = time.perf_counter()
        # the CNN was trained on 44.1 kHz input: feed it native-rate audio, as the app does
        out["key"][m] = (estimate_key(y44, 44100, method=m) if m == "cnn" else estimate_key(y, SR, method=m)).camelot
        out["secs"][f"key:{m}"] = time.perf_counter() - t0
    return out


def summarize(index: list[dict], preds: dict[str, dict], tempo_methods, key_methods) -> dict:
    summary = {"tempo": {}, "key": {}}
    for ref_field in ("bpm_beatport", "bpm_expert"):
        for m in tempo_methods:
            rows = [(preds[i["id"]]["tempo"][m], i[ref_field]) for i in index if i["id"] in preds and i.get(ref_field)]
            if not rows:
                continue
            secs = [preds[i["id"]]["secs"][f"tempo:{m}"] for i in index if i["id"] in preds]
            summary["tempo"].setdefault(ref_field, {})[m] = {
                "n": len(rows),
                "accuracy1": 100 * sum(accuracy1(p, r) for p, r in rows) / len(rows),
                "accuracy2": 100 * sum(accuracy2(p, r) for p, r in rows) / len(rows),
                "sec_per_track": sum(secs) / len(secs),
            }
    for m in key_methods:
        rows = [(preds[i["id"]]["key"][m], i["key"]) for i in index if i["id"] in preds and i.get("key")]
        if not rows:
            continue
        secs = [preds[i["id"]]["secs"][f"key:{m}"] for i in index if i["id"] in preds]
        summary["key"][m] = {
            "n": len(rows),
            "mirex": sum(mirex_score(p, r) for p, r in rows) / len(rows),
            "exact": 100 * sum(p == r for p, r in rows) / len(rows),
            "sec_per_track": sum(secs) / len(secs),
        }
    return summary


def write_report(summary: dict) -> None:
    lines = [f"# Banco de precisión — Fase 2 ({date.today().isoformat()})", "",
             "Generado por `engine/bench/run.py` sobre el audio de GiantSteps Key (Zenodo 1095691).", ""]
    names = {"bpm_beatport": "BPM de Beatport (metadatos originales en Zenodo)", "bpm_expert": "BPM experto, anotaciones v2 de GiantSteps Tempo (pistas comunes)"}
    for ref, rows in summary["tempo"].items():
        lines += [f"## Tempo: {names.get(ref, ref)}", "", "| Método | N | Accuracy1 | Accuracy2 | s/pista |", "|---|---|---|---|---|"]
        for m, r in rows.items():
            lines.append(f"| {m} | {r['n']} | {r['accuracy1']:.1f} % | {r['accuracy2']:.1f} % | {r['sec_per_track']:.2f} |")
        lines.append("")
    lines += ["## Tonalidad (anotaciones de GiantSteps Key)", "", "| Método | N | MIREX | Exacta | s/pista |", "|---|---|---|---|---|"]
    for m, r in summary["key"].items():
        lines.append(f"| {m} | {r['n']} | {r['mirex']:.3f} | {r['exact']:.1f} % | {r['sec_per_track']:.2f} |")
    lines += ["", "Umbrales (spec §6): tempo Accuracy2 ≥ 90 %, tonalidad MIREX ≥ 0,80."]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tempo", default="librosa")
    ap.add_argument("--key", default="edma,temperley,krumhansl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    tm, km = [x for x in a.tempo.split(",") if x], [x for x in a.key.split(",") if x]
    index = [i for i in json.loads(INDEX.read_text(encoding="utf-8")) if not i["id"].startswith("._")]
    if a.limit:
        index = index[: a.limit]
    preds: dict[str, dict] = {}
    failed = 0
    with ProcessPoolExecutor(a.workers) as pool:
        futs = {pool.submit(_analyze, i, tm, km): i for i in index}
        for n, f in enumerate(as_completed(futs), 1):
            try:
                r = f.result()
                preds[r["id"]] = r
            except Exception as e:  # unreadable clip: counted, not fatal
                failed += 1
                print("failed", futs[f]["id"], e)
            if n % 50 == 0:
                print(f"{n}/{len(index)}", flush=True)
    summary = summarize(index, preds, tm, km)
    summary["failed"] = failed
    # merge with earlier runs so methods can be benchmarked one at a time
    if RESULTS.exists():
        old = json.loads(RESULTS.read_text(encoding="utf-8"))["summary"]
        for ref, rows in summary["tempo"].items():
            old["tempo"].setdefault(ref, {}).update(rows)
        old["key"].update(summary["key"])
        old["failed"] = old.get("failed", 0) + failed
        summary = old
    RESULTS.write_text(json.dumps({"summary": summary}, indent=1), encoding="utf-8")
    write_report(summary)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
