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
& py -m uv pip install --python $pyexe --break-system-packages --reinstall-package djengine ((Join-Path $root 'engine') + '[nn]')
if ($LASTEXITCODE -ne 0) { throw 'engine install failed' }
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
