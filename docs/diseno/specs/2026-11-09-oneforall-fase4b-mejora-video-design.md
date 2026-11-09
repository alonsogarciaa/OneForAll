# OneForAll — Fase 4b: Mejora con IA y vídeo — Especificación

- Fecha: 2026-11-09
- Estado: borrador, pendiente de revisión del dueño
- Base: `docs/diseno/specs/2026-11-01-dj-app-design.md` (§8, hoja de ruta) y la Fase 4a (en `main`).
- Referencia: [Apollo](https://github.com/JusperLee/Apollo) (Kai Li y Yi Luo, CC BY-SA 4.0). Pesos `JusperLee/Apollo` en Hugging Face: `pytorch_model.bin`, 66,5 MB.

## 1. Objetivo

1. **Mejorar audio:** restaurar con IA las canciones bajadas de YouTube, que llegan comprimidas. Apollo repara los artefactos de compresión y reconstruye los agudos por encima de unos 16 kHz, para que suenen mejor en equipos grandes.
2. **Exportar vídeo:** crear un MP4 para pinchar con vídeo (VirtualDJ, Serato Video) o para redes. Usa el vídeo original de YouTube y, si no lo hay, la portada fija.

Éxito: la mejora se oye en la escucha a ciegas del dueño y es asumible en tiempo (§7). El vídeo exportado está sincronizado con el audio, también en las copias con otro BPM.

## 2. Decisiones

| Tema | Decisión |
|---|---|
| Tipo de mejora | Restaurar la compresión con Apollo (elegido por el dueño). Sin masterización ni loudness. |
| Cálculo | Apollo en PyTorch, en la CPU, por trozos. Reutiliza el `torch` de Demucs y no añade dependencias. |
| GPU | Apollo en ONNX con `onnxruntime-directml`, como acelerador opcional. Solo se activa si pasa la puerta de §7.2. Si no la pasa, la fase sigue solo con la CPU. |
| Dónde se guarda | **Lo decide el DJ en cada mejora**, en el cuadro: *copia nueva* o *reemplazar el original*, y *mismo formato* o *FLAC*. |
| Al descargar | Ajuste para mejorar cada descarga nueva automáticamente, con un modo y un formato fijados en Ajustes. |
| Vídeo | Usa el vídeo original de YouTube si existe. Si no, la portada fija. |
| Calidad del vídeo | Se elige al exportar: 720p, 1080p o la máxima disponible. |
| Formato del vídeo | MP4 con H.264 (`libx264`) y AAC a 320 kbps, con `+faststart`. |
| Fuera de alcance | Masterización, otros modelos de restauración, editar el vídeo (textos, efectos), formatos verticales, NVIDIA/CUDA. |

## 3. Mejorar audio: motor

### 3.1 Módulos (`engine/djengine/enhance/`)

| Módulo | Interfaz | Notas |
|---|---|---|
| `apollo.py` | `load_model(backend) -> Restorer`; `Restorer.restore(audio: np.ndarray, report, cancelled) -> np.ndarray` | Entrada y salida a 44,1 kHz estéreo `float32`. Trozos de 10 s con 1 s de solapamiento y fundido lineal (sin escalones de nivel). Informa del progreso y comprueba la cancelación entre trozos. El modelo se carga una vez por proceso. |
| `accel.py` | `backend() -> "directml" \| "cpu"` | Ajuste `enhance_backend`: `auto` (por defecto) o `cpu`. `auto` usa DirectML solo si `apollo.onnx` validado está presente y DirectML carga. Mismo patrón que `stems/accel.py`. |
| `models.py` | `ensure_apollo() -> Path` | Busca el modelo en `ONEFORALL_MODELS`. Si no está, lo descarga de Hugging Face y comprueba el checksum SHA-256. |
| `runner.py` | `make_enhance_runner(svc, path, mode, fmt) -> Runner`, `make_preview_runner(svc, path, start) -> Runner` | Trabajo `enhance`, con las etapas `loading_model`, `restoring` (porcentaje), `encoding` y `saving`. Trabajo `enhance_preview` para la escucha A/B. |
| `naming.py` | `enhanced_name(stem) -> str` | `"Canción (Mejorado)"`. Si el nombre ya existe, se usa `"Canción (Mejorado 2)"`. |

### 3.2 Opciones

- `mode`:
  - `copy`: escribe `<carpeta del original>/<nombre> (Mejorado).<ext>`.
  - `replace`: primero mueve el original a `<music_dir>/Originales/<nombre>.<ext>` (si existe, añade un sufijo numérico). Después escribe el archivo mejorado en la ruta original.
- `format`:
  - `same`: si el original tiene pérdida (MP3, AAC/M4A, Opus, OGG), se guarda en el mismo códec a 320 kbps (Opus y OGG a la máxima calidad del códec). Si es sin pérdida (FLAC, WAV, AIFF, ALAC), se mantiene igual, con la profundidad de bits del original.
  - `flac`: FLAC de 24 bits. Con `replace` la extensión cambia a `.flac`. La pista de la biblioteca y el sidecar de análisis pasan a la nueva ruta, y se avisa: "La ruta ha cambiado: reimporta en tu programa DJ".
- Un original de menos de 44,1 kHz se remuestrea a 44,1 kHz. Uno de más de 44,1 kHz se procesa a 44,1 kHz y la salida queda a 44,1 kHz (se avisa).

### 3.3 Qué se conserva

- **Etiquetas y portada:** se copian todas, incluidas las de Serato (GEOB, Vorbis o MP4). Se reutiliza la escritura de etiquetas de la 4a.
- **Análisis:** el BPM, la tonalidad, la rejilla y las secciones no cambian.
  - Con `copy`, el sidecar del original se copia para la copia.
  - Con `replace` y el mismo formato, el sidecar sigue valiendo.
  - En los dos casos, `lufs` y `peak_db` se recalculan sobre el archivo nuevo.
- **Marca de mejora:** la pista lleva `enhanced = 1` (columna nueva en `tracks`). Si se intenta mejorar una pista ya mejorada, el cuadro avisa: "Ya está mejorada; mejorarla otra vez no suele ayudar".
- **Historial:** se añade una entrada `enhance` con el modo.

### 3.4 Escucha A/B

`enhance_preview` restaura 15 s y los guarda en la caché temporal de la app. Los 15 s empiezan al principio de la primera sección `Estribillo/Drop`, o en el 30 % de la canción si no hay secciones. El cuadro reproduce el original y el mejorado alineados, con un botón A/B que cambia de uno a otro sin cortar. La caché se barre al cerrar el motor.

### 3.5 Al descargar

Ajustes nuevos:

- `enhance_on_download: bool = False`
- `enhance_mode: "copy" | "replace" = "replace"`
- `enhance_format: "same" | "flac" = "same"`

Con `enhance_on_download` activo, la descarga crea un trabajo hijo `enhance`, igual que `ThenStems`. Si la descarga pidió además stems, los stems se separan del archivo ya mejorado. El análisis automático se hace sobre el archivo final.

### 3.6 Rutas del servidor

- `POST /jobs/enhance` con `{path, mode, format}` devuelve `{job}`.
- `POST /jobs/enhance-preview` con `{path}` devuelve `{job}`. El resultado es `{original, enhanced, start}`: dos rutas de archivo y el inicio en segundos.
- `GET /enhance/estimate?path=` devuelve `{seconds}`. Se calcula con la velocidad medida en el banco y guardada en los ajustes tras la primera mejora.

## 4. Mejorar audio: interfaz

- Aparece **"Mejorar audio…"** en el menú de una pista y en el de una selección de la biblioteca.
- Abre una hoja de cristal con:
  - **Guardar como:** *Copia nueva* (por defecto) o *Reemplazar el original*. La opción de reemplazar muestra "El original se guarda en Originales".
  - **Formato:** *Mismo formato* (por defecto) o *FLAC*.
  - **Escuchar antes**, solo con una pista: lanza la escucha A/B. Muestra "Preparando… n %" y luego los botones *Original* / *Mejorado* con reproducir y pausa.
  - **Tiempo estimado** por canción y en total.
  - Botón **Mejorar**. Las pistas se encolan como trabajos `enhance` y su progreso aparece en la cola de trabajos.
- En **Ajustes → Descargas** aparecen "Mejorar audio al descargar", el modo y el formato.
- Las pistas mejoradas llevan un distintivo "Mejorado" en la biblioteca.

## 5. Exportar vídeo

### 5.1 Motor (`engine/djengine/export/video.py`)

- Trabajo `video_export` con `{track_ids, quality: "720" | "1080" | "max", out_dir?}`. Procesa las pistas en orden, cada una con sus etapas `fetching_video`, `rendering` (porcentaje de ffmpeg) y `saving`.
- **Origen de la imagen:**
  1. `video_id` de la pista, o si no `origin_video_id` (§5.2). yt-dlp descarga solo el vídeo, con `-f "bv*[height<=N]"` (sin límite con `max`).
     - Caché: `<videos_dir>/.cache/<video_id>-<quality>.<ext>`. Si existe, no se descarga otra vez.
  2. Si no hay `video_id`, o falla la descarga (`unavailable`, `blocked`, `offline`), se usa la portada fija.
     - Si no hay portada, se usa un fondo oscuro con el artista y el título (`drawtext`).
     - La pista queda en `fallbacks` con el motivo.
- **Audio:** siempre el archivo de la biblioteca: el original, el mejorado o la copia con otro BPM.
- **Sincronía con otro BPM:** si la pista es una copia con otro BPM (`origin_bpm` en el sidecar; `retempo` empieza a guardarlo en esta fase, y las copias anteriores sin él se tratan como originales), el vídeo se reescala con `setpts=PTS*origin_bpm/bpm`. El tono no afecta al vídeo.
- **Duración:** la salida dura lo mismo que el audio (`-shortest`). Si el vídeo es más corto, se rellena con su último fotograma (`tpad=stop_mode=clone`).
- **Codificación:**
  - `libx264 -preset veryfast -crf 20 -pix_fmt yuv420p`, `aac -b:a 320k`, `-movflags +faststart`.
  - Imagen fija: `-loop 1 -framerate 2 -tune stillimage`, escalada a la calidad elegida (720p o 1080p; con "máxima", 1080p).
- **Salida:** `<videos_dir>/<Artista - Título>.mp4`.
  - `videos_dir` es un ajuste nuevo; si es `None`, se usa `<music_dir>/Videos`.
  - Si el nombre ya existe, se añade un sufijo numérico.
  - El archivo se escribe con `_commit`, a partir de un temporal `~oneforall-*.part`.
- **Resultado:** `{exported: [{title, file}], fallbacks: [{title, reason}], failed: [{title, reason}]}`.

### 5.2 Copias y `origin_video_id`

`video_id` es `UNIQUE`, así que las copias (con otro BPM o mejoradas) no pueden heredarlo. Se añade a `tracks` una columna `origin_video_id TEXT NULL`, sin restricción de unicidad, mediante una migración idempotente. `retempo` y `enhance` (en modo copia) la rellenan con el `video_id` u `origin_video_id` del original.

### 5.3 Interfaz

- Aparece **"Exportar vídeo…"** en el menú de una pista y en el de una selección.
- La hoja tiene:
  - la calidad (720p, 1080p o máxima; por defecto 1080p);
  - la carpeta de destino ("Se guardará en …", con *Elegir carpeta…*);
  - el progreso;
  - el resultado: "n exportados · m con portada", la lista de motivos y *Mostrar en carpeta*.

## 6. Errores

| Caso | Mensaje |
|---|---|
| Modelo no disponible y sin conexión | "No se pudo descargar el modelo de mejora" |
| Archivo en uso al reemplazar | "Archivo en uso: ciérralo en tu programa DJ" (no se toca nada) |
| Disco lleno o sin permisos | "No se puede escribir en la carpeta de destino" |
| Vídeo no disponible o bloqueado | Se usa la portada fija y se avisa con el motivo (no es un error) |
| ffmpeg falla | "No se pudo crear el vídeo" y la pista va a `failed` |
| Cancelación | Se borran los temporales. Con `replace`, el original no se mueve hasta que el mejorado está codificado y listo. |

**Orden atómico de `replace`:**
1. Codificar en `~oneforall-*.part`.
2. Mover el original a `Originales/`.
3. Hacer `_commit` del mejorado a la ruta final.
4. Si falla el paso 3, devolver el original a su sitio.

## 7. Pruebas

### 7.1 Automáticas

- **Motor (pytest):**
  - `Restorer` con un modelo falso de identidad: los trozos y el solapamiento reconstruyen la entrada (error < 1e-6), con progreso y cancelación.
  - `runner`, con los dos modos y los dos formatos:
    - copia de seguridad en `Originales/`;
    - restauración del original si falla el `_commit`;
    - etiquetas y portada conservadas, y sidecar copiado o movido;
    - `enhanced = 1`, `origin_video_id` relleno y entrada en el historial.
  - Hijo `enhance` tras una descarga, con stems después.
  - Recorte de la escucha previa.
  - `video.py`: argumentos de ffmpeg para el vídeo, la imagen fija, `setpts` y `tpad`, la caché, los respaldos con motivo y la cancelación. Se usa un descargador falso que devuelve un vídeo de prueba de 5 s.
  - Migración de `origin_video_id` y `enhanced`.
- **UI (Vitest):** la hoja de mejora (opciones, aviso de pista ya mejorada, A/B, estimación), la hoja de vídeo (calidad, carpeta, resultado) y los ajustes al descargar.
- **E2E (Playwright, motor falso):** "Mejorar audio…" en modo copia crea la pista "(Mejorado)". "Exportar vídeo…" muestra el resultado con *Mostrar en carpeta*.

### 7.2 Puerta de Apollo (primera tarea del plan)

En 5 canciones reales de YouTube (Opus o AAC) del Ryzen 5 5600X:

- **Velocidad en CPU:** debe tardar como máximo 3 veces la duración de la canción. Si tarda más, se para y se consulta al dueño.
- **Calidad:** escucha a ciegas A/B del dueño. Debe preferir el mejorado en al menos 4 de 5. Si no, se para y se consulta.
- **DirectML:** relación señal/error frente a la CPU ≥ 30 dB y al menos 1,5 veces más rápido. Si no se cumple, se queda solo la CPU.

Los resultados se guardan en `docs/bench/2026-11-fase4b-apollo.md`.

## 8. Criterios de aceptación

1. La puerta de §7.2 se pasa, o el dueño decide qué hacer.
2. "Mejorar audio…" funciona en los dos modos y en los dos formatos. El original queda en `Originales/` al reemplazar, y la pista se sigue abriendo en Rekordbox, VirtualDJ y Serato.
3. La mejora al descargar funciona y se puede apagar.
4. El vídeo exportado de una canción de YouTube va sincronizado, también desde una copia con otro BPM. Sin vídeo, sale con la portada fija y el aviso.
5. Todas las pruebas pasan y la UI se ve bien en el ancho de escritorio y a 375 px.

## 9. Riesgos

- **Apollo se entrenó con MP3, no con Opus:** la puerta lo comprueba con audio real de YouTube. Si la mejora no se oye, se consulta al dueño (por ejemplo, probar un modelo Apollo de la comunidad entrenado con varios códecs, revisando su licencia).
- **Velocidad en CPU desconocida:** una canción podría tardar varios minutos. La puerta, la estimación y la cola lo hacen visible.
- **Licencia CC BY-SA 4.0 de los pesos:** vale para el uso personal del dueño. Si la app se distribuye, hay que atribuir y compartir con la misma licencia; se menciona en *Acerca de*.
- **yt-dlp y los formatos de vídeo de YouTube:** cambian a menudo. El respaldo con la portada evita que la exportación falle.
