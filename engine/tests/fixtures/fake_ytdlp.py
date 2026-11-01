"""Stand-in for yt-dlp used by tests: prints progress, writes src.webm next to -o, or fails."""
import shutil
import sys
import time
from pathlib import Path

args = sys.argv[1:]
url = args[-1]
out_tpl = args[args.index("-o") + 1]
if "private" in url:
    print("ERROR: [youtube] x: Private video. Sign in if you've been granted access", file=sys.stderr)
    sys.exit(1)
if "slow" in url:
    time.sleep(60)
for pct in ("12.0", "57.5", "100.0"):
    print(f"[download]  {pct}% of ~4.20MiB at 1.21MiB/s ETA 00:03", flush=True)
src = Path(__file__).with_name("tone.webm")
dst = Path(out_tpl.replace("%(ext)s", "webm"))
if src.exists():
    shutil.copy(src, dst)
else:
    dst.write_bytes(b"fake")
