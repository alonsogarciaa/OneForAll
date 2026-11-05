"""Download GiantSteps data for the local benchmark and build bench/data/index.json.

- Audio + key annotations: GiantSteps Key on Zenodo (record 1095691, CC BY-SA 4.0).
  The original Beatport preview URLs return 404 since 2026, so Zenodo is the only source.
- Tempo: GiantSteps Tempo audio is no longer available anywhere, so tempo is measured on the
  same 604 key clips against (a) the Beatport BPM in Zenodo's original metadata and
  (b) the expert v2 tempo annotations of GiantSteps Tempo for the clips both datasets share.

usage: python -m bench.fetch_giantsteps
"""
import hashlib
import json
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from bench.metrics import parse_key_label

DATA = Path(__file__).resolve().parent / "data"
ZENODO = "https://zenodo.org/record/1095691/files/{}.zip?download=1"
CHECKSUMS = {  # from mirdata's giantsteps_key loader
    "audio": "8ec9ade888d5a88ce435d7fda031929b",
    "keys": "775b7d17e009f5818544cf505b6a96fd",
    "original_metadata": "54181e0f34c35d9720439750d0b08091",
}
TEMPO_REPO = "https://github.com/GiantSteps/giantsteps-tempo-dataset.git"


def _md5(p: Path) -> str:
    h = hashlib.md5()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch_zenodo() -> Path:
    z = DATA / "zenodo"
    z.mkdir(parents=True, exist_ok=True)
    for name, md5 in CHECKSUMS.items():
        zp = z / f"{name}.zip"
        if not zp.exists() or _md5(zp) != md5:
            print("downloading", name)
            urllib.request.urlretrieve(ZENODO.format(name), zp)
        if _md5(zp) != md5:
            raise SystemExit(f"checksum mismatch for {zp}")
        out = z / name
        if not out.exists():
            with zipfile.ZipFile(zp) as f:
                f.extractall(out)
    return z


def _tempo_repo() -> Path:
    repo = DATA / "giantsteps-tempo-dataset"
    if not repo.exists():
        subprocess.run(["git", "clone", "-q", "--depth", "1", TEMPO_REPO, str(repo)], check=True)
    return repo


def _beatport_bpm(z: Path) -> dict[str, float]:
    """id -> BPM from Zenodo's original Beatport metadata (one JSON per track)."""
    out: dict[str, float] = {}
    for p in (z / "original_metadata").rglob("*.json"):
        try:
            meta = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except ValueError:
            continue
        bpm = meta.get("bpm") if isinstance(meta, dict) else None
        if bpm:
            out[p.name.split(" ")[0]] = float(bpm)  # files are "<id> Artist - Title.json"
    return out


def _expert_bpm(repo: Path) -> dict[str, float]:
    out = {}
    for p in (repo / "annotations_v2" / "tempo").glob("*.bpm"):
        v = float(p.read_text().split()[0])
        if v > 0:
            out[p.name.split(".")[0]] = v
    return out


def main() -> None:
    z = _fetch_zenodo()
    expert = _expert_bpm(_tempo_repo())
    beatport = _beatport_bpm(z)
    index = []
    for audio in sorted((z / "audio").rglob("*.mp3")):
        if audio.name.startswith("._"):  # macOS AppleDouble files inside the zip
            continue
        tid = audio.name.split(" ")[0]
        key_files = list((z / "keys").rglob(f"{tid} *.txt"))
        key = parse_key_label(key_files[0].read_text(encoding="utf-8", errors="replace").strip()) if key_files else None
        index.append({"id": tid, "audio": str(audio), "key": key,
                      "bpm_beatport": beatport.get(tid), "bpm_expert": expert.get(tid)})
    (DATA / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"audio {len(index)} | key {sum(1 for i in index if i['key'])} | "
          f"beatport bpm {sum(1 for i in index if i['bpm_beatport'])} | expert bpm {sum(1 for i in index if i['bpm_expert'])}")


if __name__ == "__main__":
    main()
