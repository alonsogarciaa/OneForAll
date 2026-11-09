"""Apollo gate (phase 4b, Task 1): CPU speed and blind A/B listening pairs.

Usage: python -m bench.apollo_gate <file>... [--seconds 30]
For each file: restores an excerpt starting at 30 % of the song, prints seconds of compute per second of audio,
and writes NN-A.wav / NN-B.wav (original and restored in random order) to bench/data/apollo/.
The real order goes to key.json: do not open it until the listening is done.
"""
import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from djengine.enhance.apollo import SR, ApolloRestorer, load_audio

OUT = Path(__file__).resolve().parent / "data" / "apollo"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--seconds", type=float, default=30.0)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    r = ApolloRestorer.shared()
    key, rows = {}, []
    for i, f in enumerate(args.files, 1):
        y = load_audio(Path(f))
        a = int(y.shape[1] * 0.3)
        x = y[:, a : a + int(args.seconds * SR)]
        t = time.perf_counter()
        z = r.restore(x, lambda p: None, lambda: False)
        rtf = (time.perf_counter() - t) / (x.shape[1] / SR)
        z = np.clip(z, -1, 1)
        pair = [("original", x), ("mejorado", z)]
        random.shuffle(pair)
        for tag, (label, audio) in zip("AB", pair):
            sf.write(OUT / f"{i:02d}-{tag}.wav", audio.T, SR, subtype="PCM_24")
        key[f"{i:02d}"] = {"file": Path(f).name, "A": pair[0][0], "B": pair[1][0]}
        rows.append((Path(f).name, round(rtf, 2)))
        print(f"{i:02d} {Path(f).name}: {rtf:.2f} s per s of audio")
    (OUT / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    print("mean", round(sum(r for _, r in rows) / len(rows), 2))


if __name__ == "__main__":
    main()
