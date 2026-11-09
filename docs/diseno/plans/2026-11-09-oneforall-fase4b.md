# OneForAll Fase 4b (mejora con IA y vídeo) — Plan de implementación

**Goal:** Restaurar audio comprimido con Apollo (copia o reemplazo, mismo formato o FLAC, también al descargar) y exportar MP4 con el vídeo original de YouTube o con la portada.

**Architecture:**
- Paquete nuevo `engine/djengine/enhance/`. Contiene un `Restorer` por trozos (Apollo en PyTorch o ONNX/DirectML) y los runners `enhance` y `enhance_preview`, que siguen el patrón de `prep/retempo.py`.
- Exportar vídeo vive en `engine/djengine/export/video.py`, con un descargador de vídeo inyectable en `Services`.
- En la UI hay dos hojas de cristal nuevas, abiertas desde la biblioteca, igual que `RetempoSheet` y `DjExportSheet`.

**Tech Stack:** Python 3 + FastAPI + torch (ya instalado con Demucs) + onnxruntime-directml (ya instalado) + ffmpeg + yt-dlp. React + Zustand + Vitest. Playwright Electron.

**Spec:** `docs/diseno/specs/2026-11-09-oneforall-fase4b-mejora-video-design.md`

## Global Constraints

- No hay dependencias nuevas de Python ni de npm. El código del modelo Apollo se incluye en `engine/djengine/vendor/apollo/`, con su licencia CC BY-SA 4.0 y la atribución a Kai Li y Yi Luo.
- Modelo: `JusperLee/Apollo` → `pytorch_model.bin`, de 66,5 MB, con el SHA-256 fijado en `enhance/models.py`. Se incluye en `build/runtime/models/apollo/`.
- Audio para Apollo: 44,1 kHz estéreo, `float32`. Trozos de 10 s con 1 s de solapamiento y fundido lineal.
- Los textos de la UI son exactamente los de la spec (en español).
- Los nombres de etapa del motor son `loading_model`, `restoring`, `encoding`, `saving`, `fetching_video` y `rendering`.
- Los archivos se mueven a su sitio con `pipelines._commit` desde temporales `~oneforall-*.part`. Los nombres libres se buscan con `naming.unique_path`.
- La UI se comprueba en el ancho de escritorio y a 375 px.
- No se hace push.

## Review Focus

1. **Reemplazar un archivo abierto en el programa DJ:** debe dar "Archivo en uso: ciérralo en tu programa DJ" y dejar el original intacto en su ruta. Prueba en la Tarea 4.
2. **Original de 48 kHz o mono:** la salida debe quedar a 44,1 kHz estéreo y con la misma duración, con un error de ±1 trozo. Prueba en la Tarea 1.
3. **Canción más corta que un trozo (< 10 s) o con un último trozo de pocas muestras:** no debe dar error ni dejar un clic en la unión. Prueba en la Tarea 1.
4. **Copia con otro BPM cuyo original no tiene `video_id`, o vídeo borrado:** debe salir con la portada y el aviso, sin fallar. Prueba en la Tarea 7.
5. **Mejorar dos veces la misma pista en paralelo (doble clic o selección con duplicados):** solo debe correr un trabajo por ruta. Prueba en la Tarea 4.

---

### Task 1: Apollo por trozos y prueba de calidad y velocidad (PUERTA)

**Files:**
- Create: `engine/djengine/vendor/apollo/__init__.py`, `engine/djengine/vendor/apollo/model.py`, `engine/djengine/vendor/apollo/LICENSE.md`
- Create: `engine/djengine/enhance/__init__.py`, `engine/djengine/enhance/models.py`, `engine/djengine/enhance/apollo.py`
- Create: `engine/bench/apollo_gate.py`, `docs/bench/2026-11-fase4b-apollo.md`
- Modify: `build/fetch-runtime.ps1` (descargar el modelo en `models/apollo/`)
- Test: `engine/tests/enhance/test_apollo.py`

**Interfaces:**
- Produces:
  - `enhance.models.apollo_path() -> Path`, que lanza `UserError("model_missing", "No se pudo descargar el modelo de mejora")`. Orden de búsqueda: `ONEFORALL_MODELS/apollo/pytorch_model.bin`, la caché `<app data>/models/apollo/` y, por último, la descarga con verificación del SHA-256.
  - `enhance.apollo.Restorer` (Protocol), con `restore(audio: np.ndarray, progress: Callable[[float], None], cancelled: Callable[[], bool]) -> np.ndarray`: entrada y salida `(2, n) float32` a 44,1 kHz; lanza `JobCancelled`.
  - `enhance.apollo.FakeRestorer`, la identidad por trozos, para pruebas y para el modo `--fake`.
  - `enhance.apollo.get_restorer(svc) -> Restorer` devuelve `FakeRestorer` si `svc.fake` o `ONEFORALL_FAKE_ENHANCE=1`. Si no, devuelve `ApolloRestorer.shared(backend)`.
  - `enhance.apollo.chunks(n: int, sr: int = 44100, size_s: float = 10, overlap_s: float = 1) -> list[tuple[int, int]]`.
  - `enhance.apollo.stitch(pieces: list[np.ndarray], spans, n: int, overlap: int) -> np.ndarray`.
  - `enhance.apollo.load_audio(path: Path) -> np.ndarray`, que decodifica a `(2, n)` a 44,1 kHz con ffmpeg. Si el original es mono, duplica el canal.

- [ ] **Step 1: Pruebas de trozos y de unión**

```python
def test_chunks_cover_everything_with_overlap():
    sp = chunks(44100 * 25)
    assert sp[0] == (0, 441000) and sp[-1][1] == 44100 * 25
    assert all(b[0] == a[1] - 44100 for a, b in zip(sp, sp[1:]))

def test_short_song_is_one_chunk():
    assert chunks(44100 * 3) == [(0, 44100 * 3)]

def test_identity_restorer_rebuilds_input():
    x = np.random.default_rng(0).standard_normal((2, 44100 * 23)).astype(np.float32)
    seen = []
    y = FakeRestorer().restore(x, seen.append, lambda: False)
    assert y.shape == x.shape and np.max(np.abs(y - x)) < 1e-6
    assert seen[-1] == 1.0

def test_tail_shorter_than_overlap(): ...  # n = 10 s + 300 muestras: misma forma, error < 1e-6
def test_cancel_between_chunks(): ...      # cancelled() pasa a True tras el 1.º trozo → JobCancelled
def test_load_audio_48k_mono(tmp_path): ...  # tono de 3 s, 48 kHz mono, hecho con ffmpeg → forma (2, 132300 ± 1)
```

- [ ] **Step 2:** Ejecutar `cd engine && pytest tests/enhance/test_apollo.py -v`. Resultado esperado: FAIL (falta el módulo).
- [ ] **Step 3: Implementar `chunks`, `stitch`, `FakeRestorer` y `load_audio`**
  - `stitch` aplica un fundido lineal en cada solapamiento: la rampa de salida del trozo anterior y la de entrada del siguiente suman 1.
  - El último trozo se alinea al final (`start = n - size`) cuando `n > size`, para no tener un trozo diminuto.
- [ ] **Step 4: Incluir Apollo y crear `ApolloRestorer`**
  - Copiar la clase del modelo del repositorio `JusperLee/Apollo` (`look2hear/models/apollo.py` y sus capas) a `vendor/apollo/model.py`, sin dependencias de Lightning ni Hydra, con la cabecera de licencia.
  - `ApolloRestorer.shared(backend)` carga el `state_dict` una vez, con `torch.no_grad()` y `torch.set_num_threads(os.cpu_count())`.
  - `restore` usa `chunks` y `stitch`, y llama a `progress(i / total)`.
  - `models.py` sigue el patrón de `stems/models.py`.
- [ ] **Step 5:** Ejecutar `pytest tests/enhance -v`. Resultado esperado: PASS.
- [ ] **Step 6: Script de la puerta `engine/bench/apollo_gate.py <archivo>...`**
  - Por cada canción: el tiempo de restauración en CPU, la proporción tiempo / duración y los dos archivos WAV de escucha a ciegas en `engine/bench/data/apollo/`, con los nombres `NN-A.wav` y `NN-B.wav` y el orden decidido al azar.
  - El orden real se guarda en `key.json`, que no se enseña hasta después de la escucha.
- [ ] **Step 7:** Añadir la descarga del modelo a `fetch-runtime.ps1` y ejecutar el script con 5 canciones reales de YouTube de la biblioteca del dueño. Anotar los tiempos en `docs/bench/2026-11-fase4b-apollo.md`.
- [ ] **Step 8: Commit**: `feat(enhance): Apollo restorer by chunks + gate bench`.
- [ ] **Step 9: PARAR y consultar al dueño.**
  - Hay que pasarle las 5 parejas A/B para su escucha a ciegas.
  - Se sigue solo si se cumplen dos condiciones: la proporción es ≤ 3 y prefiere el mejorado en ≥ 4 de 5.
  - Su resultado se anota en el banco.

### Task 2: DirectML opcional

**Files:**
- Create: `engine/djengine/enhance/accel.py`, `engine/bench/apollo_accel.py`
- Modify: `engine/djengine/settings.py` (`enhance_backend: Literal["auto", "cpu"] = "auto"`), `engine/djengine/enhance/apollo.py`
- Test: `engine/tests/enhance/test_accel.py`

**Interfaces:**
- Produces: `enhance.accel.backend(settings) -> Literal["directml", "cpu"]`, una copia del patrón de `stems/accel.py` con `ONNX_MODEL = "apollo.onnx"` y `VALIDATION = "apollo_validated.json"`, en el mismo `onnx_dir()`.

- [ ] **Step 1: Pruebas**: `backend` devuelve `cpu` en cuatro casos: sin el ONNX, con `passed: false`, sin el proveedor `DmlExecutionProvider` (simulado con monkeypatch de `_providers`) y con `enhance_backend="cpu"`. Devuelve `directml` cuando se cumple todo.
- [ ] **Step 2:** Ejecutar y comprobar que fallan. Después implementar `accel.py` y la rama ONNX de `ApolloRestorer` (`onnxruntime.InferenceSession` con `["DmlExecutionProvider", "CPUExecutionProvider"]`, entrada de un trozo de 10 s).
- [ ] **Step 3: Probar ONNX en la GPU**: `apollo_accel.py` exporta un trozo de 10 s con `torch.onnx.export` (opset 17) y lo compara con la CPU en las 5 canciones de la puerta.
  - Escribe `apollo_validated.json` con `passed` igual a `snr_db >= 30 and speedup >= 1.5`.
  - Anota los resultados en el banco.
  - Si la exportación a ONNX falla, se anota, `passed` queda en `false` y se sigue con la CPU.
- [ ] **Step 4:** Ejecutar `pytest tests/enhance -v` (PASS) y hacer commit: `feat(enhance): optional DirectML backend behind a quality gate`.

### Task 3: Biblioteca y retempo: `enhanced`, `origin_video_id`, `origin_bpm`

**Files:**
- Modify: `engine/djengine/library.py` (migración, `TrackRecord`, setters), `engine/djengine/prep/retempo.py`
- Test: `engine/tests/test_library.py`, `engine/tests/prep/test_retempo.py` (o el archivo que ya prueba retempo)

**Interfaces:**
- Produces:
  - `TrackRecord` gana `enhanced: bool = False` y `origin_video_id: str | None = None`, al final y con valores por defecto, para que siga siendo compatible con las llamadas posicionales.
  - `Library.video_source(track: TrackRecord) -> str | None` devuelve `video_id or origin_video_id`.
  - `Library.update_track_path(old: str, new: str, fmt: str) -> None`.
  - `Library.set_enhanced(path: str) -> None`.
  - El sidecar de una copia de retempo gana `"origin_bpm": float`.

- [ ] **Step 1: Pruebas**
  - La migración añade las columnas `enhanced INTEGER NOT NULL DEFAULT 0` y `origin_video_id TEXT`, y dos aperturas seguidas no fallan.
  - `retempo` deja la copia con el `origin_video_id` del original y el sidecar con `origin_bpm == base_bpm`.
  - `video_source` también funciona en una copia de una copia.
  - `update_track_path` mueve la fila sin perder `bpm` ni `camelot`.
- [ ] **Step 2:** Ejecutar y comprobar que fallan. Después implementar: la migración, añadida a la tupla de la Fase 2; en `retempo`, el `origin_video_id=svc.library.video_source(track)` al crear el `TrackRecord`; y `"origin_bpm": base_bpm` en el sidecar de `_light_analysis`.
- [ ] **Step 3:** Ejecutar `pytest -q` (todo en PASS) y hacer commit: `feat(library): enhanced flag, origin_video_id, retempo origin_bpm`.

### Task 4: Trabajo `enhance`

**Files:**
- Create: `engine/djengine/enhance/runner.py`
- Modify: `engine/djengine/server.py` (`EnhanceJobBody`, `"enhance": 1` en la concurrencia, `GET /enhance/estimate`), `engine/djengine/settings.py` (`enhance_rtf: float | None = None`)
- Test: `engine/tests/enhance/test_runner.py`, `engine/tests/test_server_enhance.py`

**Interfaces:**
- Consumes:
  - `get_restorer` y `load_audio` (Tarea 1).
  - `Library.set_enhanced`, `update_track_path` y `video_source` (Tarea 3).
  - `read_tags`, `read_cover`, `write_tags` y `set_bpm_key` de `tags.py`, y `_commit` y `unique_path`.
- Produces:
  - `enhance.runner.enhanced_name(stem: str) -> str` devuelve `"X (Mejorado)"`.
  - `enhance.runner.target_codec(path: Path, fmt: Literal["same", "flac"]) -> tuple[str, list[str]]`, que da la extensión y los argumentos de ffmpeg:
    - `mp3`: `libmp3lame -b:a 320k`
    - `m4a`/`aac`: `aac -b:a 320k`
    - `opus`: `libopus -b:a 256k`
    - `ogg`: `libvorbis -q:a 10`
    - `flac`: `flac`, con la misma profundidad de bits
    - `wav`: `pcm_s16le` o `pcm_s24le`, según el original
    - `aif`/`aiff`: `pcm_s16be` o `pcm_s24be`
    - `fmt="flac"`: `flac -sample_fmt s32` (24 bits)
  - `enhance.runner.make_enhance_runner(svc, path: Path, mode: Literal["copy", "replace"], fmt: Literal["same", "flac"]) -> Runner`, que devuelve el resultado `{"path": str, "moved_from": str | None, "backup": str | None}`.
  - `enhance.runner.submit_enhance(svc, path: Path, mode, fmt, then_stems: ThenStems | None = None) -> Job`. Si ya hay un trabajo `enhance` de la misma ruta sin terminar, lo devuelve en lugar de crear otro.
  - Cuerpo `POST /jobs` `{"type": "enhance", "path", "mode", "format"}`.
  - `GET /enhance/estimate?path=` devuelve `{"seconds": float | None}`, calculado como `duration * enhance_rtf`.

- [ ] **Step 1: Pruebas** (con `ONEFORALL_FAKE_ENHANCE=1` y archivos creados con ffmpeg):
  - `copy` con `same` sobre un MP3: crea `Song (Mejorado).mp3`, conserva el título, el artista y la portada, añade la pista a la biblioteca con `enhanced=1` y el `origin_video_id` del original, copia el sidecar (BPM y rejilla iguales, LUFS recalculado) y añade una entrada `enhance` al historial.
  - `replace` con `same`: el original queda en `<music_dir>/Originales/Song.mp3`, la ruta final es la misma y la pista tiene `enhanced=1`.
  - `replace` con `flac`: `Song.flac` existe, `Song.mp3` está en `Originales/` y la fila de la biblioteca y el sidecar apuntan a `.flac`.
  - Si `_commit` falla en `replace` (monkeypatch que lanza `OSError`), el original vuelve a su ruta y el error es `disk`.
  - **Archivo en uso:** si `os.replace` lanza `PermissionError` al mover el original, el resultado es `UserError("file_busy", "Archivo en uso: ciérralo en tu programa DJ")` y el original sigue intacto.
  - Si se cancela durante `restoring`, no queda ningún `.part` y el original no se ha tocado.
  - Dos `submit_enhance` seguidos con la misma ruta devuelven el mismo trabajo.
  - Tabla de `target_codec`: un caso por cada extensión.
  - Servidor: `POST /jobs` con `type: "enhance"` da 200, con un `mode` inválido da 422, y `/enhance/estimate` devuelve `null` sin `enhance_rtf`.
- [ ] **Step 2:** Ejecutar y comprobar que fallan.
- [ ] **Step 3: Implementar el runner**
  - **Restauración:** etapas `loading_model` (0), `restoring` (de 0 a 85, con el progreso por trozos, con `asyncio.to_thread` y `ctx.check_cancelled` entre trozos) y `encoding` (de 85 a 95, escribiendo con ffmpeg en `ctx.tmp_dir/out.<ext>` y conservando la frecuencia de muestreo original solo si es 44,1 kHz; si no, 44,1 kHz).
  - **Guardado:** etapa `saving`, después de `begin_finalize`, en este orden:
    1. Escribir las etiquetas en el temporal.
    2. En `replace`, mover el original a `Originales/` con `unique_path`.
    3. Hacer `_commit` del temporal a la ruta final.
    4. Si falla el paso 3, devolver el original con `os.replace` y relanzar el error.
  - **Análisis:** se copia o se mueve el sidecar con `svc.analysis` (BPM, rejilla y secciones se mantienen); se recalculan `lufs` y `peak_db` con `analysis.loudness.measure` y se hace `restamp`.
  - **Estimación:** al terminar, se guarda `enhance_rtf = tiempo de restoring / duración` (media móvil 0,7 / 0,3) en los ajustes.
- [ ] **Step 4:** Ejecutar `pytest -q` (PASS) y hacer commit: `feat(enhance): enhance job (copy/replace, same/FLAC) with backup and rollback`.

### Task 5: Escucha A/B (`enhance_preview`)

**Files:**
- Modify: `engine/djengine/enhance/runner.py`, `engine/djengine/server.py` (`EnhancePreviewJobBody`, `"enhance_preview": 1`)
- Test: `engine/tests/enhance/test_preview.py`

**Interfaces:**
- Produces:
  - `enhance.runner.preview_start(sidecar: dict | None, duration: float) -> float`: el inicio de la primera sección `Estribillo/Drop`; si no hay, `0.3 * duration`. Se limita a `max(0, duration - 15)`.
  - `make_preview_runner(svc, path) -> Runner` devuelve `{"original": str, "enhanced": str, "start": float}`. Los dos son WAV de 15 s en `svc.paths.tmp_dir/preview/` y se añaden a `svc.allowed_paths` para que `/audio` los sirva.
  - Cuerpo `{"type": "enhance_preview", "path"}`.

- [ ] **Step 1: Pruebas**:
  - `preview_start` en tres casos: con estribillo, sin secciones y con una canción de 10 s, que da 0.
  - Con el restaurador falso, el runner crea dos WAV de 15 s ± 1 trozo, y `allowed_paths` los contiene.
  - Al arrancar el motor, la carpeta `preview/` se vacía (se reutiliza el barrido de los temporales).
- [ ] **Step 2:** Ejecutar y comprobar que fallan. Después implementar y ejecutar `pytest -q` (PASS).
- [ ] **Step 3: Commit**: `feat(enhance): 15 s A/B preview job`.

### Task 6: Mejorar al descargar

**Files:**
- Modify: `engine/djengine/settings.py`, `engine/djengine/pipelines.py`
- Test: `engine/tests/test_pipelines_enhance.py`

**Interfaces:**
- Consumes: `submit_enhance` (Tarea 4).
- Produces: los ajustes `enhance_on_download: bool = False`, `enhance_mode: Literal["copy", "replace"] = "replace"` y `enhance_format: Literal["same", "flac"] = "same"`.

- [ ] **Step 1: Pruebas** con el motor falso:
  - Con `enhance_on_download` apagado, no se crea ningún trabajo `enhance`.
  - Encendido, se crea un `enhance` de nivel superior (no hijo, igual que `submit_stems`) con el modo y el formato de los ajustes.
  - Con `then_stems` y la mejora a la vez, la descarga **no** lanza los stems. Los lanza el `enhance` al terminar, sobre su ruta de resultado.
  - Con la mejora encendida, el análisis automático corre sobre el archivo final:
    - en `replace` con `same`, la descarga lo lanza como siempre;
    - en `copy` o con `flac`, lo lanza `enhance` sobre el resultado.
- [ ] **Step 2:** Ejecutar y comprobar que fallan. Implementar en `make_download_runner`:
  - Si `enhance_on_download`: `submit_enhance(svc, final, mode, fmt, then_stems=req.then_stems)` y no `submit_stems`.
  - `submit_analysis` solo si `not enhance_on_download or (mode == "replace" and fmt == "same")`. El runner `enhance` llama a `submit_analysis` sobre el resultado cuando la ruta cambia y `analyze_on_download` está activo.
- [ ] **Step 3:** Ejecutar `pytest -q` (PASS) y hacer commit: `feat(enhance): enhance on download, stems after enhance`.

### Task 7: Trabajo `video_export`

**Files:**
- Create: `engine/djengine/export/video.py`
- Modify: `engine/djengine/download.py` (`download_video`), `engine/djengine/fakes.py` (`fake_video_downloader`), `engine/djengine/server.py` (`Services.video_downloader`, `VideoExportJobBody`, `"video_export": 1`), `engine/djengine/settings.py` (`videos_dir: str | None = None`)
- Test: `engine/tests/export/test_video.py`

**Interfaces:**
- Consumes: `Library.video_source` (Tarea 3), `origin_bpm` del sidecar (Tarea 3), `read_cover`, `_commit`, `unique_path` y `sanitize_filename`.
- Produces:
  - `download.download_video(ctx, url: str, quality: Literal["720", "1080", "max"], dest: Path) -> Path` usa yt-dlp con `-f "bv*[height<=N][vcodec^=avc1]/bv*[height<=N]"` (sin `[height<=N]` con `max`), `--no-playlist` y la salida en `dest`. Los errores se traducen con `map_ytdlp_error`.
  - `fakes.fake_video_downloader` crea un vídeo de prueba de 5 s con `lavfi testsrc`. Un ID con "private" da `unavailable`.
  - `export.video.video_args(audio: Path, image: Path, still: bool, quality: str, speed: float, out: Path) -> list[str]`. Es una función pura y se prueba sola.
  - `export.video.make_video_export_runner(svc, track_ids: list[int], quality, out_dir: str | None) -> Runner` devuelve `{"exported": [{title, file}], "fallbacks": [{title, reason}], "failed": [{title, reason}]}`.
  - Cuerpo `{"type": "video_export", "track_ids": [int] (min 1), "quality": "720"|"1080"|"max" = "1080", "out_dir": str | None}`.

- [ ] **Step 1: Pruebas**
  - `video_args`:
    - **Vídeo:** contiene `-c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p`, `-c:a aac -b:a 320k`, `-movflags +faststart` y `-shortest`, y en el filtro aparece `tpad=stop_mode=clone`.
    - **`speed=124/128`:** el filtro contiene `setpts=PTS*1.032258` (es decir, 128 / 124 con 6 decimales).
    - **Imagen fija:** contiene `-loop 1 -framerate 2 -tune stillimage`, y `scale` a 1920 de ancho en `1080` y en `max`, y a 1280 de ancho en `720`.
  - Runner, con los descargadores falsos:
    - Una pista con `video_id` da un MP4 en `<music_dir>/Videos/Artista - Título.mp4`, con la duración del audio ± 0,1 s, medida con `ffprobe`.
    - **Caché:** un segundo export no vuelve a llamar al descargador (contador).
    - Una copia de retempo usa el vídeo del original con `setpts`.
    - Una pista sin `video_id` sale con la portada y queda en `fallbacks` con el motivo "Sin vídeo original".
    - Un vídeo con "private" sale con la portada y queda en `fallbacks` con el motivo "Este vídeo ya no está disponible".
    - Sin portada, se usa el fondo con `drawtext`.
    - Si ffmpeg falla (monkeypatch de `find_tool` a un ejecutable que devuelve 1), la pista queda en `failed` con "No se pudo crear el vídeo" y las demás siguen.
    - Si se cancela, no queda ningún `.part`.
- [ ] **Step 2:** Ejecutar y comprobar que fallan.
- [ ] **Step 3: Implementar**
  - El progreso global es `(i + pct_pista) / n`. Etapas: `fetching_video`, `rendering` (con `out_time_us` de ffmpeg) y `saving`.
  - La caché del vídeo está en `<videos_dir>/.cache/<id>-<quality>.<ext>`.
  - La imagen fija es la portada (`read_cover`) guardada en `tmp/cover.jpg`. Si no hay portada, `-f lavfi -i color=c=0x111114:s=1920x1080` y `drawtext` con el artista y el título. Se usa la fuente `C:/Windows/Fonts/segoeui.ttf` si existe; si no, la fuente por defecto de ffmpeg.
- [ ] **Step 4:** Ejecutar `pytest -q` (PASS) y hacer commit: `feat(export): video export with original YouTube video or cover fallback`.

### Task 8: UI de Mejorar audio

**Files:**
- Create: `ui/src/components/EnhanceSheet.tsx`, `ui/src/components/EnhanceSheet.test.tsx`
- Modify:
  - `ui/src/lib/engineClient.ts` (`enhance`, `enhancePreview`, `enhanceEstimate`)
  - `ui/src/lib/types.ts` (`TrackRecord.enhanced`)
  - `ui/src/stores/uiStore.ts` (`enhanceFor: string[] | null`, `openEnhance`, `closeEnhance`)
  - `ui/src/App.tsx`
  - `ui/src/screens/LibraryScreen.tsx` (botón "Mejorar audio…" y distintivo "Mejorado")
  - `ui/src/components/DataSheet.tsx` (botón)
  - `ui/src/components/JobRow.tsx` (etapas `restoring: 'Mejorando'`, `fetching_video: 'Bajando vídeo'`, `rendering: 'Creando vídeo'`)
  - `ui/src/components/datasheet.css`

**Interfaces:**
- Consumes: los cuerpos y rutas de las Tareas 4 y 5.
- Produces:
  - `client.enhance(path: string, mode: 'copy' | 'replace', format: 'same' | 'flac') => Promise<{ job: Job }>`
  - `client.enhancePreview(path: string) => Promise<{ job: Job }>`
  - `client.enhanceEstimate(path: string) => Promise<{ seconds: number | null }>`

- [ ] **Step 1: Pruebas (Vitest)**
  - Valores por defecto: *Copia nueva* y *Mismo formato*. Con *Reemplazar el original* aparece "El original se guarda en Originales".
  - **Mejorar** con dos rutas llama a `client.enhance` dos veces con el modo y el formato elegidos, y cierra la hoja.
  - Una pista con `enhanced: true` muestra "Ya está mejorada; mejorarla otra vez no suele ayudar".
  - **Escuchar antes**, solo si hay una ruta: lanza `enhancePreview` y muestra "Preparando… 40 %". Cuando el trabajo termina, aparecen los botones *Original* y *Mejorado* (`aria-pressed`).
  - La estimación muestra "≈ 2 min por canción · 4 min en total" con `seconds: 120` y dos rutas, y no se muestra si es `null`.
- [ ] **Step 2:** Ejecutar `npx vitest run ui/src/components/EnhanceSheet.test.tsx` (FAIL). Después implementar la hoja con `GlassSheet` y `datasheet.css`.
  - La escucha A/B usa dos `<audio>` con la URL `/audio`, sincronizados. *A/B* cambia `muted` sin parar la reproducción.
- [ ] **Step 3:** Ejecutar `npx vitest run` (PASS). Comprobar la hoja en el navegador a 375 px y en el ancho de escritorio.
- [ ] **Step 4: Commit**: `feat(ui): Mejorar audio sheet with A/B preview`.

### Task 9: UI de vídeo y ajustes

**Files:**
- Create: `ui/src/components/VideoExportSheet.tsx`, `ui/src/components/VideoExportSheet.test.tsx`
- Modify:
  - `ui/src/lib/engineClient.ts` (`videoExport`)
  - `ui/src/stores/uiStore.ts` (`videoExport: { trackIds: number[] } | null`)
  - `ui/src/App.tsx`
  - `ui/src/screens/LibraryScreen.tsx` (botón "Exportar vídeo…", activo con al menos 1 pista seleccionada)
  - `ui/src/screens/SettingsScreen.tsx`:
    - **Descargas:** "Mejorar audio al descargar", el modo y el formato.
    - **Carpetas:** "Carpeta de vídeos".
    - **Acerca de:** añadir "La mejora de audio usa Apollo (Kai Li y Yi Luo), con licencia CC BY-SA 4.0."

**Interfaces:**
- Produces: `client.videoExport(trackIds: number[], quality: '720' | '1080' | 'max', outDir?: string) => Promise<{ job: Job }>`.

- [ ] **Step 1: Pruebas (Vitest)**
  - Hoja de vídeo:
    - La calidad por defecto es 1080p.
    - "Se guardará en <music_dir>/Videos", o la carpeta elegida.
    - **Exportar** llama a `videoExport` con las pistas y la calidad.
    - Con el trabajo en curso, muestra "Exportando… 30 %".
    - Con el resultado, muestra "2 exportados · 1 con portada", la lista de motivos y *Mostrar en carpeta*, que abre la carpeta del primer archivo.
  - Ajustes:
    - Al encender el interruptor se guarda `{enhance_on_download: true}`.
    - Las opciones de modo y formato solo se ven con el interruptor encendido.
- [ ] **Step 2:** Ejecutar (FAIL), implementar y ejecutar `npx vitest run` (PASS). Comprobar en el navegador a 375 px y en el ancho de escritorio.
- [ ] **Step 3: Commit**: `feat(ui): video export sheet and enhance settings`.

### Task 10: E2E, instalador y resumen

**Files:**
- Modify: `e2e/app.spec.ts`, `build/fetch-runtime.ps1` (si la Tarea 1 no lo dejó hecho), `electron-builder.yml` (solo si hace falta para `models/apollo`)
- Create: `docs/diseno/fase4b-resumen.md`

- [ ] **Step 1: E2E** (motor falso):
  - "Mejorar audio…" con *Copia nueva* hace que aparezca "Fake Song (Mejorado)" en la biblioteca.
  - "Exportar vídeo…" muestra "1 exportados" y *Mostrar en carpeta*.
- [ ] **Step 2:** Ejecutar todas las suites: `cd engine && pytest -q`, `npx vitest run` y `npx playwright test`. Todo debe pasar.
- [ ] **Step 3:** Ejecutar `npm run dist`. El instalador debe incluir `resources/runtime/models/apollo/pytorch_model.bin`; comprobarlo listando `out` o `dist/win-unpacked`.
- [ ] **Step 4:** Escribir el resumen (qué se hizo, cifras de las pruebas, resultados de la puerta y pruebas pendientes del dueño) y hacer commit: `docs: phase 4b summary`.
