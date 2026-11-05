# OneForAll

Windows desktop app for DJs: search YouTube Music, download tracks and playlists, convert formats, keep a tagged library, and analyse BPM, key (Camelot), loudness and waveform. Electron + React UI with a local Python engine.

## Development

```bash
cd engine && py -m uv sync --extra nn   # engine (Python 3.12)
npm install                              # app
npm run dev                              # run the app
npx vitest run                           # UI tests
cd engine && py -m uv run pytest -q      # engine tests
npm run build && npx playwright test     # end-to-end tests
```

Installer: `powershell -File build/fetch-runtime.ps1` then `npm run dist`.

Accuracy benchmark (local only, downloads GiantSteps from Zenodo): `cd engine && py -m uv run python -m bench.fetch_giantsteps && py -m uv run python -m bench.run`. Results: `docs/bench/`.

## Third-party components and licences

| Component | Licence | Note |
|---|---|---|
| madmom (code, vendored in `engine/djengine/vendor/madmom`) | BSD-2-Clause | Compiled extensions replaced by stubs; only the key CNN path is used |
| madmom key model (`models/key/2018/key_cnn.pkl`) | CC BY-NC-SA 4.0 | **Non-commercial use only.** Replace before selling or distributing commercially |
| DeepRhythm (tempo CNN) | AGPL-3.0 | Fine for personal use; distributing the app requires offering its source under AGPL |
| Demucs (code and `htdemucs_6s` weights) | MIT | Stem separation (Meta / Défossez et al.) |
| audio-separator | MIT | Runs the UVR karaoke model |
| UVR-MDX-NET Karaoke 2 model | Author's terms (UVR community model) | Lead / backing vocal split; personal use |
| yt-dlp | Unlicense | |
| FFmpeg (gyan.dev essentials build) | GPL-3.0 | Shipped as a separate executable |
| librosa, numpy, scipy, pyloudnorm, mutagen, FastAPI | ISC / BSD / MIT | |
| GiantSteps Key dataset (benchmark only, never shipped) | CC BY-SA 4.0 | Faraldo et al.; Zenodo record 1095691 |

YouTube's Terms of Service do not allow downloading; use the app only with content you have the right to download.
