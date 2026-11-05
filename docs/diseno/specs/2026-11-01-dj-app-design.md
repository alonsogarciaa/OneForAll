# OneForAll — Especificación de diseño

- Fecha: 2026-11-01
- Nombre: "OneForAll" 
- Estado: pendiente de revisión
- Fuentes: conversación de diseño, `review.txt` (app anterior), `Liquid_Glass.md` (estética)

## 1. Objetivo

App de escritorio para un DJ aficionado que permite buscar música en YouTube desde la propia app, descargar pistas y playlists, convertir formatos, analizar BPM y tonalidad, separar stems y gestionar una biblioteca propia. Estética Apple / Liquid Glass: translúcida, limpia, nítida.

Éxito = el usuario busca una canción, la descarga en el formato deseado con etiquetas correctas, la encuentra en su biblioteca y (fases siguientes) obtiene BPM/tonalidad fiables y stems, sin los bugs de la app anterior.

## 2. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Fuente de música | Solo YouTube / YouTube Music (yt-dlp + ytmusicapi). Uso bajo responsabilidad del usuario (los ToS de YouTube prohíben descargar). |
| Plataforma | Windows 11 primero. Código multiplataforma; empaquetado Mac en Fase 6. |
| Stack | Electron + React + TypeScript (UI) y motor Python (sidecar). |
| Software DJ destino | Rekordbox, Serato, VirtualDJ, Traktor: etiquetas estándar legibles por todos. |
| Formatos | Conversión entre cualquier formato; mejora de audio con IA opcional (Fase 4). |
| Aceleración IA | Independiente del fabricante: CUDA (NVIDIA) > DirectML (AMD/Intel/NVIDIA en Windows) > CoreML (Mac) > CPU, vía ONNX Runtime. |
| Estética | `Liquid_Glass.md`. Sin maquetas previas; se verifica en la app. |
| Fuera de alcance | Plugin VST (proyecto aparte). |

## 3. Arquitectura

```
Electron
 ├─ main (Node): ventana acrylic/vibrancy, ciclo de vida del motor, aviso al cerrar
 ├─ preload: API tipada expuesta al renderer (contextIsolation, sin nodeIntegration)
 └─ renderer (React): Buscar · Descargas · Biblioteca · Historial · Conversor · Ajustes
        │ HTTP + WebSocket en 127.0.0.1, puerto aleatorio, token por sesión
Motor Python (paquete `djengine`, FastAPI + uvicorn)
 ├─ api        rutas REST + WS /events
 ├─ jobs       cola de trabajos, cancelación, temporales por trabajo
 ├─ search     ytmusicapi (+ yt-dlp de respaldo)
 ├─ download   yt-dlp + ffmpeg
 ├─ convert    ffmpeg
 ├─ tags       mutagen
 ├─ naming     nombres de archivo y colisiones
 ├─ library    SQLite
 ├─ accel      selección de backend ONNX (Fase 3+)
 └─ [F2] analysis · [F3] stems · [F4] enhance, timepitch, export · [F5] discover, importers
```

### 3.1 Arranque del motor
- Electron lanza el Python embebido con `--port 0 --token <aleatorio>`.
- El motor escribe una línea JSON en stdout `{"port": N}` cuando está listo.
- Todas las peticiones llevan la cabecera `X-Token`. El motor solo escucha en `127.0.0.1`.
- Si el proceso muere, main lo reinicia (máx. 3 intentos/minuto) y la UI muestra "Reconectando motor…".

### 3.2 Empaquetado (Windows)
- electron-builder → instalador NSIS `.exe`.
- Incluye: Python 3.12 embebido con dependencias, ffmpeg estático, yt-dlp.
- yt-dlp se actualiza desde la app (Ajustes → "Actualizar yt-dlp" y comprobación al arrancar, como máximo 1 vez/día).
- Modelos de IA (Fases 3–4) se descargan bajo demanda la primera vez que se usan, no van en el instalador.

### 3.3 Rutas
- Datos de la app: `%APPDATA%/OneForAll/` (`library.db`, `settings.json`, `tmp/`, `models/`, `logs/`).
- Música: configurable, por defecto `Música/OneForAll/`. Las playlists van a `Música/OneForAll/<Nombre playlist>/`.

## 4. API del motor (Fase 1)

| Método | Ruta | Uso |
|---|---|---|
| GET | `/search?q=&kind=songs\|videos\|playlists` | Resultados de búsqueda |
| GET | `/playlist/{id}` | Pistas de una playlist |
| POST | `/jobs` | Crear trabajo (`download` o `convert`) |
| GET | `/jobs` | Trabajos activos y recientes |
| DELETE | `/jobs/{id}` | Cancelar un trabajo (y sus hijos) |
| GET | `/jobs/active-count` | Para el aviso al cerrar |
| GET | `/library?q=` | Pistas de la biblioteca |
| GET | `/library/duplicate?videoId=&artist=&title=` | Comprobación de duplicado |
| GET | `/history` · DELETE `/history` (body: `ids` o `all`) | Historial |
| GET / PUT | `/settings` | Ajustes |
| POST | `/tools/ytdlp/update` | Actualizar yt-dlp |
| WS | `/events` | `job.progress`, `job.done`, `job.failed`, `job.cancelled`, `engine.notice` |

`job.progress` = `{id, parentId?, stage, pct, speed?, eta?}`. Etapas: `queued`, `downloading`, `converting`, `tagging`, `finalizing`.

## 5. Modelo de trabajos

- Un `JobManager` con colas por tipo: descarga (3 en paralelo por defecto), conversión (2). Fases siguientes añaden análisis y stems, cada una con su cola propia.
- **Cada trabajo trabaja en `tmp/<jobId>/`.** El archivo final se mueve a su destino solo al terminar con éxito (renombrado atómico).
- **Cancelar** = matar el árbol de subprocesos (yt-dlp/ffmpeg) + borrar `tmp/<jobId>/` + emitir `job.cancelled`. No queda ningún residuo en la carpeta de destino. (Bug review: "archivos residuales").
- Al arrancar, el motor borra los `tmp/*` huérfanos.
- **Cancelación por proceso:** cada trabajo tiene su botón. Cancelar uno no toca los demás. La UI reinicia la barra y la animación del trabajo cancelado. (Bugs/implementaciones review.)
- **Playlist** = trabajo padre + un hijo por pista. Si una pista falla, las demás siguen. Al final, resumen "N descargadas, M fallidas" con reintento de las fallidas. Cancelar el padre cancela los hijos pendientes y en curso; los ya terminados se conservan.

## 6. Fase 1 — requisitos detallados

### 6.1 Buscador
- Fuente principal: ytmusicapi. Pestañas: **Canciones** (filtro `songs`, por defecto), **Vídeos** (remixes, sesiones, mezclas), **Playlists**.
- Cada resultado muestra: carátula, título, artista, duración, visualizaciones (si la fuente las da) y un indicador "Ya en tu biblioteca".
- Respaldo si ytmusicapi falla: `yt-dlp ytsearch` filtrado (categoría Música, duración 1–20 min en Canciones).
- Resultados sin título o duración, o que no son contenido de audio, se descartan antes de mostrarse. (Bug review: "resultados bugeados".)
- Al pulsar un resultado se abre un panel de detalle (cristal) con los datos y las acciones de descarga.
- Pegar una URL de YouTube o YouTube Music en el buscador la resuelve directamente (pista o playlist).

### 6.2 Descarga
- Botón principal "Descargar" con el formato por defecto, más un menú en píldora para elegir otro formato y calidad.
- Antes de descargar, comprobación de duplicado (§6.5).
- Descarga de la mejor pista de audio disponible (`bestaudio`) y después conversión al formato elegido.
- La UI no muestra textos de BPM/KEY en la Fase 1. (Bug review: "se procesará al descargar" sin la opción activa.) En la Fase 2 solo se muestran si el análisis está activado.

### 6.3 Nombres de archivo
- Plantilla configurable, por defecto `{artist} - {title}`.
- Se eliminan los caracteres no válidos en Windows (`<>:"/\|?*`) y los nombres reservados (`CON`, `NUL`…). Longitud máxima 180 caracteres.
- **Colisión:** `Nombre (1).ext`, `Nombre (2).ext`… en la **misma carpeta**. Nunca se crean subcarpetas por colisión. (Bug review #1.)
- Solo se crean carpetas para playlists, y solo con el nombre de la playlist.

### 6.4 Conversión
- Formatos: MP3 (CBR 128–320, VBR V0), AAC/M4A, ALAC, OPUS, OGG Vorbis, FLAC, WAV, AIFF, y "Original" (sin recodificar).
- Opciones avanzadas: frecuencia de muestreo (44.1/48/96 kHz) y profundidad (16/24 bit) para los formatos sin pérdida.
- Aviso visible: pasar audio de YouTube a un formato sin pérdida no aumenta la calidad. Para eso está "Mejorar audio" (Fase 4).
- Pantalla Conversor: arrastrar y soltar archivos propios o elegirlos de la biblioteca → formato → convertir. Cada archivo es un trabajo cancelable. El original no se modifica; la salida aplica las mismas reglas de nombres.

### 6.5 Biblioteca, duplicados e historial
- SQLite (`library.db`):
  - `tracks(id, video_id UNIQUE NULL, title, artist, album, duration_s, views, path, format, bitrate, cover_path, added_at, bpm NULL, musical_key NULL, camelot NULL)`
  - `history(id, track_id NULL, video_id, title, artist, action, status, at)`
  - `playlists(id, yt_id, name, path, added_at)`, `playlist_tracks(playlist_id, track_id, position)`
- Las columnas BPM y tonalidad quedan creadas desde la Fase 1 para no migrar después.
- **Duplicado:** mismo `video_id`, o coincidencia de artista + título normalizados (minúsculas, sin acentos, sin "(Official Video)", "ft."…). Aviso en panel: "Ya tienes esta canción" → *Abrir ubicación* / *Descargar igualmente* / *Cancelar*.
- Si un archivo de la biblioteca ya no existe en disco, se marca como "no encontrado" (no se borra solo).
- **Historial:** selección múltiple → "Borrar seleccionadas", o "Borrar todo" (con confirmación). Borrar del historial no borra archivos.
- Historial y biblioteca muestran duración y visualizaciones (BPM y tonalidad en la Fase 2).

### 6.6 Etiquetas
- mutagen: título, artista, álbum, año, carátula (miniatura recortada a cuadrado, 600 px), URL de origen en el comentario.
- La Fase 2 escribe el BPM y la tonalidad en los campos estándar: ID3 `TBPM`/`TKEY`, MP4 `tmpo`, Vorbis `BPM`/`INITIALKEY`. Son los que leen Rekordbox, Serato, VirtualDJ y Traktor.

### 6.7 Avisos y cierre
- Avisos importantes (duplicado, errores, resumen de playlist, confirmaciones) → panel de cristal modal centrado. Los avisos menores van como toasts. (Mejora review: avisos en ventana propia.)
- Al cerrar con trabajos activos: diálogo "Hay N procesos en curso (descargas/conversiones). ¿Cerrar y cancelarlos?". Si se confirma, los trabajos se cancelan limpiamente antes de salir.

### 6.8 Ajustes
- Carpeta de música, formato y calidad por defecto, plantilla de nombre, descargas en paralelo, modo "Tintado" (más opacidad), actualizar yt-dlp, abrir carpeta de logs.
- Desde la Fase 3: backend de aceleración (Automático / GPU / CPU) y carpeta de stems.

### 6.9 Errores
Los errores de yt-dlp se traducen a mensajes claros con su acción:

| Causa | Mensaje / acción |
|---|---|
| Vídeo privado o eliminado | "Este vídeo ya no está disponible" |
| Restricción de edad o región | "YouTube bloquea este vídeo (edad/región)" |
| Sin red | "Sin conexión" + reintentar |
| Extractor roto | "YouTube ha cambiado; actualiza yt-dlp" + botón actualizar |
| Disco lleno o sin permisos | "No se puede escribir en <carpeta>" + cambiar carpeta |

Todos los errores se registran en `logs/engine.log` (rotación 5 × 2 MB).

## 7. Interfaz (Liquid Glass)

- **Ventana:** Electron `backgroundMaterial: 'acrylic'` en Windows 11 (`vibrancy` en Mac). Barra de título integrada, tamaño mínimo 1024×640.
- **Estructura:** barra lateral izquierda de cristal más opaco (navegación), barra superior con el buscador en píldora, contenido central sobre superficie oscura semisólida, panel inferior de descargas activas (mini cola, desplegable).
- **Tokens:** paleta y variables de `Liquid_Glass.md` (`--lg-*`). Modo oscuro por defecto y modo claro adaptado. Acento System Blue `#007AFF`. Desenfoque ≤ 20 px.
- **Tipografía:** Inter (texto e interfaz), Plus Jakarta Sans 600 (títulos). Fuentes incluidas en la app, sin dependencia de Google Fonts en tiempo de ejecución.
- **Reglas:** máximo 2 capas de cristal superpuestas. El cristal solo en navegación, paneles flotantes, controles en píldora y la mini cola. Las listas y tablas van sobre superficie sólida para que se lean bien. Texto < 14 px nunca directamente sobre cristal. Radios: 16–24 px en paneles y píldoras en botones. Transiciones con `cubic-bezier` y `prefers-reduced-motion` respetado.
- **Modo Tintado:** sube la opacidad del cristal al 70 %.
- Durante la implementación se usan las skills `impeccable` y `ui-ux-pro-max`.

## 8. Fases siguientes (hoja de ruta revisada el 2026-11-02)

Se incorporan todas las funciones de [stemdeck](https://github.com/stemdeckapp/stemdeck) a petición del dueño. Cada fase tiene su propia spec.

| Fase | Contenido |
|---|---|
| **2. Análisis** | BPM, tonalidad (Camelot), loudness, forma de onda, rejilla de beats, tap tempo, ventana de datos, buscador armónico. Spec: `2026-11-02-oneforall-fase2-analisis-design.md` |
| **3. Stems + mezclador** | 6 stems (`htdemucs_6s`), voz principal/coros (UVR-MDX-NET Karaoke 2), elegir stems antes de separar, cola, aceleración NVIDIA/AMD/Intel/CPU, carpeta de stems elegible, "solo voz/batería/bajo" desde el buscador. Mezclador de práctica: silencio, solo y volumen por stem, velocidad 0,5–0,99× sin cambiar el tono, bucle sobre la onda, cambio de tonalidad global o por stem, metrónomo con cuenta atrás y compases. Exportar mezcla, zip de stems y bucle; arrastrar al DAW |
| **4. Herramientas** | Mejora de audio con IA, cambiar BPM y tono del archivo, editar la rejilla de beats, detección de secciones, Rekordbox XML, exportar vídeo con la imagen original |
| **5. Descubrimiento y datos** | Recomendaciones por canción y por texto, búsqueda en SoundCloud, importar enlaces de Spotify/Apple Music/SoundCloud, ficha de MusicBrainz/Wikipedia/Discogs, letras sincronizadas (LRCLIB) y transcripción de la voz |
| **6. Biblioteca y extras** | Carpetas de colores, #etiquetas, favoritos, papelera, modo guía, acceso desde el móvil por la red local, idiomas, aviso de actualizaciones, empaquetado para Mac |

## 9. Estructura del proyecto

```
app/         Electron main + preload (TypeScript)
ui/          React + Vite (TypeScript)
engine/      paquete Python djengine + pyproject.toml
engine/tests pytest
build/       scripts de empaquetado (Python embebido, ffmpeg, yt-dlp)
docs/        specs y planes
```

## 10. Pruebas

- **Motor (pytest):**
  - Nombres y colisiones.
  - Cancelación con limpieza de temporales (subproceso simulado).
  - Duplicados y normalización.
  - Esquema de la base de datos.
  - Conversión real con audio generado por ffmpeg (tono senoidal) a cada formato.
  - Escritura y lectura de etiquetas.
  - Mapeo de errores de yt-dlp.
  - Descarga con yt-dlp simulado.
  - Prueba online opcional (`-m online`) contra YouTube, fuera de la ejecución por defecto.
- **UI:** Vitest para componentes y Playwright sobre Electron para los flujos buscar → descargar → biblioteca, cancelar y aviso al cerrar.
- **Verificación visual:** capturas de la app a 1024×640 y 1920×1080, en modo oscuro, modo claro y modo Tintado.

## 11. Criterios de aceptación — Fase 1

1. Buscar "la graciosa quevedo" en Canciones devuelve la canción en los primeros resultados, sin vídeos ajenos a la música.
2. Descargar una pista produce `Artista - Título.mp3` (320 kbps) con carátula y etiquetas, y aparece en la biblioteca y el historial.
3. Descargar la misma pista otra vez muestra el aviso de duplicado. Si se elige "Descargar igualmente", se crea `… (1).mp3` en la misma carpeta.
4. Una playlist de 10 pistas se descarga en su carpeta. Una pista no disponible no detiene las demás y aparece en el resumen.
5. Cancelar una descarga o conversión a mitad no deja archivos en el destino ni en `tmp/`, y no afecta a otros trabajos.
6. Cerrar con trabajos activos muestra el aviso.
7. Convertir un archivo propio a FLAC, WAV, AIFF, OPUS y M4A produce archivos válidos.
8. El historial permite borrar las seleccionadas y borrar todo.
9. El instalador `.exe` funciona en un Windows sin Python ni ffmpeg instalados.

## 12. Riesgos

- **Cambios de YouTube** rompen yt-dlp o ytmusicapi → actualización desde la app y buscador de respaldo.
- **Tamaño del instalador** (~300 MB en la Fase 1; los modelos de IA se descargan bajo demanda en fases siguientes).
- **Precisión de BPM y tonalidad** → se decide con un banco de pruebas medido, no a ojo.
- **DirectML + modelos de stems:** compatibilidad por verificar al inicio de la Fase 3, con la CPU siempre como respaldo.
