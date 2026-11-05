# Prepares build/runtime for the installer:
#   runtime/python  portable CPython 3.12 (uv-managed build) with the engine installed
#   runtime/bin     ffmpeg.exe, ffprobe.exe (gyan.dev essentials) and yt-dlp.exe (GitHub release)
# Idempotent: existing pieces are kept unless -Force is given.
param([switch]$Force)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $PSScriptRoot 'runtime'
$bin = Join-Path $runtime 'bin'
$dl = Join-Path $runtime '_dl'
$py = Join-Path $runtime 'python'
New-Item -ItemType Directory -Force $bin, $dl | Out-Null

function Get-Verified([string]$url, [string]$out, [string]$expected) {
    Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing
    $actual = (Get-FileHash $out -Algorithm SHA256).Hash.ToLower()
    if ($expected -and $actual -ne $expected.ToLower()) { throw "Checksum mismatch for $url" }
}

# --- ffmpeg ---------------------------------------------------------------------
if ($Force -or -not (Test-Path (Join-Path $bin 'ffmpeg.exe'))) {
    $zip = Join-Path $dl 'ffmpeg.zip'
    $base = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
    $sum = (Invoke-WebRequest -Uri "$base.sha256" -UseBasicParsing).Content.Trim().Substring(0, 64)
    Get-Verified $base $zip $sum
    $x = Join-Path $dl 'ffmpeg-x'
    if (Test-Path $x) { Remove-Item -Recurse -Force $x }
    Expand-Archive $zip $x
    Get-ChildItem $x -Recurse -Include ffmpeg.exe, ffprobe.exe | Copy-Item -Destination $bin -Force
    Remove-Item -Recurse -Force $x
}

# --- yt-dlp ---------------------------------------------------------------------
if ($Force -or -not (Test-Path (Join-Path $bin 'yt-dlp.exe'))) {
    $rel = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download'
    $sums = (Invoke-WebRequest -Uri "$rel/SHA2-256SUMS" -UseBasicParsing).Content -split "`n"
    $line = $sums | Where-Object { $_ -match '\syt-dlp\.exe$' } | Select-Object -First 1
    Get-Verified "$rel/yt-dlp.exe" (Join-Path $bin 'yt-dlp.exe') ($line -split '\s+')[0]
}

# --- Python + engine ---------------------------------------------------------------
if ($Force -and (Test-Path $py)) { Remove-Item -Recurse -Force $py }
if (-not (Test-Path (Join-Path $py 'python.exe'))) {
    $src = (& py -m uv python find 3.12).Trim()
    if (-not $src) { throw 'Python 3.12 not found; run: py -m uv python install 3.12' }
    Copy-Item -Recurse (Split-Path -Parent $src) $py
}
$pyexe = Join-Path $py 'python.exe'
# exact versions from uv.lock, then the engine itself without re-resolving its dependencies
$reqs = Join-Path $env:TEMP 'oneforall-runtime-reqs.txt'
& py -m uv export --project (Join-Path $root 'engine') --extra nn --no-dev --no-hashes --no-emit-project --format requirements-txt -o $reqs
if ($LASTEXITCODE -ne 0) { throw 'lockfile export failed' }
& py -m uv pip install --python $pyexe --break-system-packages -r $reqs
if ($LASTEXITCODE -ne 0) { throw 'dependency install failed' }
& py -m uv pip install --python $pyexe --break-system-packages --no-deps --reinstall-package djengine (Join-Path $root 'engine')
if ($LASTEXITCODE -ne 0) { throw 'engine install failed' }
Remove-Item $reqs
& $pyexe -c "import djengine, fastapi, yt_dlp, ytmusicapi, mutagen, PIL, psutil, librosa, torch, deeprhythm; import djengine.analysis.key_cnn; print('runtime ok')"
if ($LASTEXITCODE -ne 0) { throw 'runtime import check failed' }

# --- DeepRhythm weights (otherwise downloaded on first analysis) -------------------------
$models = Join-Path $runtime 'models'
New-Item -ItemType Directory -Force $models | Out-Null
$weights = Join-Path $models 'deeprhythm-0.7.pth'
if ($Force -or -not (Test-Path $weights)) {
    & $pyexe -c "from deeprhythm.utils import get_weights; import shutil, sys; shutil.copy(get_weights(quiet=True), sys.argv[1])" $weights
    if ($LASTEXITCODE -ne 0) { throw 'deeprhythm weights fetch failed' }
}

# --- Separation models (otherwise downloaded on first use) -------------------------------
$torchHome = Join-Path $models 'torch'
$uvr = Join-Path $models 'uvr'
$hf = Join-Path $models 'hf'
New-Item -ItemType Directory -Force $torchHome, $uvr, $hf | Out-Null
$env:TORCH_HOME = $torchHome
$env:HF_HOME = $hf
$env:PATH = $bin + ';' + $env:PATH  # audio-separator shells out to ffmpeg
& $pyexe -c "from demucs.pretrained import get_model; get_model('htdemucs_6s'); print('demucs model ok')"
if ($LASTEXITCODE -ne 0) { throw 'demucs model fetch failed' }
& $pyexe -c "import sys; from audio_separator.separator import Separator; s = Separator(model_file_dir=sys.argv[1], output_dir=sys.argv[1]); s.load_model(model_filename='UVR_MDXNET_KARA_2.onnx'); print('uvr model ok')" $uvr
if ($LASTEXITCODE -ne 0) { throw 'karaoke model fetch failed' }
Remove-Item Env:\TORCH_HOME
Remove-Item Env:\HF_HOME
# separation smoke test with the bundled weights only
$env:ONEFORALL_MODELS = $models
& $pyexe -c "import numpy as np; from djengine.stems.demucs_sep import DemucsSeparator; out = DemucsSeparator().separate(np.zeros((2, 88200), dtype=np.float32), 44100, lambda f: None, lambda: False); assert len(out) == 6; print('separation ok')"
if ($LASTEXITCODE -ne 0) { throw 'separation smoke test failed' }
# analysis models must really run (an import alone would let a silent fallback ship)
& $pyexe -c "import numpy as np; from djengine.analysis import tempo_deeprhythm as td, key_cnn as kc; sr = 22050; t = np.arange(sr * 20) / sr; y = (np.sin(2 * np.pi * 440 * t) * (np.mod(t, 0.5) < 0.05)).astype(np.float32); td._get(); r = td.deeprhythm_tempo(y, sr, 70, 180); assert r.bpm > 0, r; p = kc.probabilities(np.repeat(y, 2), 44100); assert p.shape[-1] == 24, p.shape; print('analysis models ok', r.bpm)"
if ($LASTEXITCODE -ne 0) { throw 'analysis models smoke test failed' }
Remove-Item Env:\ONEFORALL_MODELS
