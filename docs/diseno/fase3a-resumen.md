# Fase 3a: resumen de ejecución

Rama `fase3` (2026-11-02). Aceleración: `docs/bench/2026-11-fase3a-accel.md`.

## Decisiones tomadas (con su coste si fueran erróneas)

- Task 2: Ruling: folder name from library track, else file tags, else file stem; Services gains stems store; separator raises JobCancelled itself (protocol) — cost if wrong: none
- Task 3: Demucs htdemucs_6s CPU: 10 s audio ~5 s (Ryzen 5600X). Ruling: added fast identity-model test for the 60 s block cross-fade (only exercised by songs > 60 s); slow/bench markers excluded from default pytest — cost if wrong: none
- Task 4: Ruling: karaoke as classes (FakeKaraoke/UvrKaraoke .split) instead of a bare function; audioread added to nn extra; bundled ffmpeg dir prepended to PATH for audio-separator (it shells out to ffmpeg by name); UVR model downloads to <data>/models/uvr when not bundled — cost if wrong: none
- Task 5: Ruling: ThenStems/StemsJobBody validate stem ids (422); library has_stems via store sources + validity; zip written to .part then replaced — cost if wrong: none
- Task 6: Ruling: renderer registers stem files via drag:allow (from /stems); main validates normalized path + audio ext + existence; drag icon build/resources/drag.png shipped as extraResource — cost if wrong: none
- Task 7: Ruling: StemsSheet hosted globally via uiStore.stemsFor (library, history, data sheet open it); estimate rate 0.4 s per audio second until job history exists (history wiring left to the sheet's caller) — cost if wrong: estimate off
- Task 8: Ruling: "Solo voz…" on a song already in the library separates the existing file instead of asking about a duplicate download — cost if wrong: none
- Task 9: Gate FAILED → CPU. ONNX export works (ORT-CPU 81/71 dB vs torch core; core 137 dB vs original forward). DirectML EP output wrong on RX 9060 XT (−43 dB; −40 dB with graph optimizations off) though 9× faster. ORT-CPU 0.97× torch. Report docs/bench/2026-11-fase3a-accel.md. Ruling: bench runs in a separate uv env with onnxruntime-directml (conflicts with the CPU onnxruntime wheel used by audio-separator); app runtime keeps CPU onnxruntime — cost if wrong: none
- Task 10: Ruling: demucs 4.x loads htdemucs_6s from the HuggingFace hub, so the runtime bundles an HF cache (models/hf, HF_HUB_OFFLINE=1) besides models/uvr; PATH gets the bundled ffmpeg for audio-separator in the fetch script — cost if wrong: none
- Task 10: Ruling (bug found by E2E): two analyses of the same file (auto after download + data sheet) raced on tag writes and left the sheet blank; submit_analysis now returns the active job for that file, the sheet shows stems without analysis and reports a missing analysis instead of staying blank (test_same_file_is_not_analysed_twice_at_once, DataSheet stems test) — cost if wrong: none

## Pendientes menores (no corregidos)

- drag allow-list is fed by the renderer (main checks extension/existence, not the engine's stem table)
- /stems/zip uses a fixed .zip.part name (double click race) and writes synchronously without progress
- is_stem_file realpaths every row on each /audio request
- stems table key not normcased (case-variant paths miss the cache)
- karaoke changes PATH from a worker thread; reloads the model each call; StopIteration if output names change
- karaoke with cached vocals still re-runs all 6 Demucs stems
- StemsSection shows "Preparando…" for karaoke/encoding/saving stages
- re-separating in another format leaves old-format files in the folder
- line-ending churn (app/preload/index.ts)

## Corregido tras la revisión final

- own tag writes (analysis, manual BPM) staling stems — StemsStore.restamp(path, before) — test_own_tag_writes_keep_stems_valid RED→GREEN, suite green
- different sources sharing one stems folder — "<Artist - Title> (n)" when another source owns it — test_different_sources_never_share_a_folder RED→GREEN
- unbounded memory on long audio — refuse > 20 min with UserError too_long before any work — test_too_long_audio_is_refused_before_any_work RED→GREEN
- non-atomic cross-drive move — reuse pipelines._commit (.part + replace, disk error) — test_failed_cross_drive_copy_leaves_no_partial_file RED→GREEN
- cancel not waiting for the worker thread (two separations at once, tmp recreated) — shield + await on cancel — test_cancel_waits_for_the_worker_thread RED→GREEN

## Aceptación

- Task 10: Acceptance §7: 1 three stems exact files ~2 min (114 s, 4:18 song) PASS; 2 lead/backing PASS; 3 search «Solo voz» (UI test + API test + DOM check) PASS; 4 cancel clean / no 2nd instance (runner + API tests, single-instance lock) PASS; 5 play / zip PASS, drag unit-tested only; 6 folder/format settings (runner + UI tests) PASS; 7 accel report present, DirectML off (gate failed) PASS
