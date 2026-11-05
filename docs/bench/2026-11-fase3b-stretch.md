# Fase 3b — Signalsmith Stretch spike (2026-11-05)

Setup: `signalsmith-stretch@1.3.2` in Chromium (desktop app browser pane), Ryzen 5 5600X. Stems: Quevedo — BUENAS NOCHES, 6 stems, MP3 320 (the DESPECHÁ stems were no longer on disk).

## Sync between nodes

The same stem was loaded into 6 nodes, each routed to its own output channel. All were scheduled at the same `output` time, with a loop of 60–66 s, rate 0.75, and a change to 0.5 scheduled at 20 s. Render: offline, 40 s. Comparison window: 25–29 s.

| Node vs node 0 | Best lag (±512) | Max abs difference |
|---|---|---|
| 1–5 | 0 samples | 0 (bit-identical) |

Nodes scheduled at the same context time stay sample-exact, including across a loop wrap and a rate change. Criterion: ≤ 128 samples. **Pass.**

## CPU

Six different stems, 20 s rendered offline (wall time / audio time, so 100 % = one core's real-time budget):

| Rate | Preset | CPU |
|---|---|---|
| 0.5 | default | 16.9 % |
| 0.75 | default | 17.0 % |
| 0.5 | cheaper | 14.7 % |

Criterion: under 40 % of one core. **Pass** with the default preset; 8 stems (karaoke) extrapolate to about 23 %.

## Not measured here

- **Listening quality at 0.5× and +3 semitones:** checked by ear on the installed app (Task 9).
- **CSP in the packaged Electron build** (`blob:` worklet, `'wasm-unsafe-eval'`): checked by the E2E test and the installed app (Task 9).
