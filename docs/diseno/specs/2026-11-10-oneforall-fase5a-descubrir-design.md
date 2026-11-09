# OneForAll — Fase 5a: Descubrir — Especificación

- Fecha: 2026-11-10
- Estado: aprobada (2026-11-10)
- Base: `docs/diseno/specs/2026-11-01-dj-app-design.md` (§8, hoja de ruta) y las Fases 1 a 4b (en `main`).
- La Fase 5 se divide en **5a (descubrir, esta spec)** y **5b (datos de la canción: ficha de MusicBrainz, Wikipedia y Discogs, letras sincronizadas y transcripción)**. Lo decidió el dueño el 2026-11-10.

## 1. Objetivo

Encontrar música nueva que encaje con la sesión y traerla de donde esté.

1. **Recomendaciones** parecidas a una canción y por moods y géneros de YouTube Music. Cada recomendación muestra su BPM y su tonalidad, calculados al vuelo, y si encaja con la referencia.
2. **SoundCloud** como fuente de búsqueda y descarga.
3. **Importar enlaces** de Spotify, Apple Music y SoundCloud. Las canciones de Spotify y Apple Music se buscan y se descargan desde YouTube.

Éxito:
- De una canción de la biblioteca salen al menos 20 recomendaciones, y el 80 % lleva BPM y tonalidad en menos de un minuto.
- Una playlist pública de Spotify de 50 canciones se empareja con al menos 45 aciertos sin revisar.

## 2. Decisiones

| Tema | Decisión |
|---|---|
| Recomendaciones "por texto" | Moods y géneros de YouTube Music (`get_mood_categories` / `get_mood_playlists`). Sin IA ni servicios de pago (elegido por el dueño). |
| Parecidas a una canción | Radio de YouTube Music: `get_watch_playlist(videoId, radio=True)`, unas 25 canciones. |
| BPM y tonalidad | Análisis al vuelo de un fragmento de 60 s de cada recomendación (elegido por el dueño). |
| Spotify | Sin cuenta: se lee la página pública de inserción. Límite aproximado de 100 canciones (elegido por el dueño). |
| Apple Music | Página pública, sin cuenta. |
| SoundCloud | yt-dlp (`scsearch`, descarga directa). Sin API ni cuenta. |
| Fuera de alcance | IA para frases libres, API oficial de Spotify, sincronizar playlists en directo, pistas Go+ de SoundCloud, cuentas de usuario. |

## 3. Recomendaciones

### 3.1 Motor

| Módulo | Interfaz | Notas |
|---|---|---|
| `discover/recs.py` | `similar(svc, video_id) -> list[SearchResult]`; `moods(svc) -> list[{section, items: [{title, params}]}]`; `mood_playlists(svc, params) -> list[SearchResult]` | Usa el `ytm` de `SearchService`. Filtra con `filter_results` (sin vídeos de menos de 60 s ni sin título) y quita la propia canción y los duplicados por `video_id`. Una canción de la biblioteca sin `video_id` usa la primera coincidencia de "artista título" en YouTube Music como semilla. |
| `discover/preview.py` | `fetch_clip(ctx, url, start_s, seconds=60) -> Path`; `quick_analysis(path) -> {bpm, camelot, tonic, mode}` | yt-dlp `-f bestaudio --download-sections "*{start}-{start+60}"`, con el inicio en el 30 % de la duración. Para el análisis se reutilizan `decode`, `estimate_tempo` y `estimate_key` del analizador, sin sonoridad, forma de onda, rejilla ni secciones. El BPM se pliega al rango de Ajustes. |
| `discover/store.py` | tabla `quick_analysis(video_id TEXT PRIMARY KEY, bpm REAL, tonic TEXT, mode TEXT, camelot TEXT, failed INTEGER, at TEXT)` | Caché permanente por `video_id`. Si una pista ya está en la biblioteca y analizada, se usa ese análisis. |
| `discover/runner.py` | trabajo `quick_analysis` con `{video_ids: [...]}` | Concurrencia 2. Va pista a pista y emite un evento `quick.result {video_id, bpm, camelot, failed}` por cada una. Se puede cancelar (al salir de la pantalla). Los fallos quedan en caché con `failed=1` durante 24 h. |
| `discover/fit.py` | `fit(ref_bpm, ref_camelot, bpm, camelot) -> "encaja" \| "cerca" \| None` | **Encaja:** Camelot compatible (`compatible` ≠ None) y BPM a ±6 %, contando también el doble y la mitad. **Cerca:** solo una de las dos condiciones. Sin datos, None. |

Rutas:
- `GET /discover/similar?video_id=` o `?track_id=` devuelve `[SearchResult + {bpm, camelot, fit}]`, con el análisis que ya esté en caché.
- `GET /discover/moods`.
- `GET /discover/mood?params=`.
- `POST /jobs` con `{type: "quick_analysis", video_ids}`.

### 3.2 Interfaz

- **Pantalla "Descubrir"** en la barra lateral, entre Buscar y Descargas, con dos pestañas:
  - **Parecidas a…:** selector de una pista de la biblioteca. En la biblioteca y en la ficha de datos hay un botón "Parecidas" que abre esta pestaña con esa pista.
  - **Moods y géneros:** fichas de moods y géneros; al pulsar una, aparecen sus playlists y luego sus canciones. La referencia se pone a mano (BPM y tonalidad, opcionales).
- **Filas:** las mismas que en el buscador (escuchar, descargar, "Ya la tienes"), más las columnas BPM y Tonalidad y el distintivo **Encaja** o **Cerca**. Mientras se analiza, la fila muestra "analizando…"; si falla, "—".
- **Ordenar:** "Orden de YouTube" o "Mejor encaje". El análisis de las filas visibles arranca solo al abrir la lista.

## 4. SoundCloud

- **Buscador:** pestaña nueva "SoundCloud".
  - Usa `yt-dlp --flat-playlist -J "scsearch25:<texto>"`.
  - El resultado es un `SearchResult` con `kind="soundcloud"`, `id="sc:<id>"` y `url` = la URL de la pista.
  - Filtro: duración ≥ 60 s.
- **Descarga:** el mismo trabajo `download`, ya que yt-dlp lee SoundCloud. La pista se guarda con `video_id = "sc:<id>"`, así que el duplicado y "Ya la tienes" funcionan igual.
- **Go+:** una pista que solo deja oír 30 s (la duración que da yt-dlp en la previsualización ≤ 31 s, o el flag `preview`) se marca "Solo vista previa" y no se puede descargar.

## 5. Importar enlaces

### 5.1 Motor (`discover/links.py`)

- `parse_link(text) -> {service: "spotify" | "apple" | "soundcloud", kind: "track" | "album" | "playlist", id, url} | None`. El buscador ya detecta los enlaces de YouTube; este añade los demás.
- `read_spotify(kind, id) -> ImportList`:
  - Lee `https://open.spotify.com/embed/{kind}/{id}` y extrae el JSON de `<script id="__NEXT_DATA__">`.
  - Toma el nombre de la lista y cada canción: título, artistas y duración en ms.
  - Si la estructura no está, da `UserError("source_changed", "Spotify ha cambiado; actualiza la app")`.
- `read_apple(url) -> ImportList`:
  - Lee la página pública y extrae el JSON de `<script id="serialized-server-data">`.
  - Toma el nombre y las canciones: título, artista y duración.
  - Si la estructura no está, da el mismo `source_changed` con "Apple Music".
- `read_soundcloud(url) -> ImportList`: `yt-dlp --flat-playlist -J`. No hace falta emparejar, porque cada entrada ya es descargable.
- `ImportList = {name, service, items: [{title, artist, duration_s}]}`.

### 5.2 Emparejado (`discover/match.py`)

- `match(svc, item) -> {status: "found" | "review" | "missing", best: SearchResult | None, alternatives: [SearchResult] (≤ 3)}`.
- Busca `"{artist} {title}"` en YouTube Music (canciones) con `SearchService.search`.
- **Puntuación** = `0.6 · parecido_título + 0.3 · parecido_artista + 0.1 · duración`:
  - Los parecidos se calculan con `difflib.SequenceMatcher` sobre `normalize_key`.
  - La duración puntúa 1 si difiere ≤ 5 s y 0 si difiere más de 15 s.
- **Estado:**
  - `found` si la mejor puntuación es ≥ 0,8.
  - `review` si está entre 0,5 y 0,8.
  - `missing` si no hay resultados o la mejor es < 0,5.
- Concurrencia 4, con un trabajo `import_match` que emite `match.result` por cada canción.

### 5.3 Interfaz

- Al pegar en el buscador un enlace de Spotify, Apple Music o SoundCloud se abre la hoja **"Importar"** con el nombre de la lista y su origen.
- **Filas:** título y artista originales, y el emparejado:
  - ✓ con la canción de YouTube elegida;
  - "Revisar" con un desplegable de hasta 3 alternativas y "Ninguna";
  - "No encontrada".
- Opciones de formato, iguales que en las playlists.
- El botón **Descargar todas (n)** crea una playlist en la biblioteca con el nombre original y descarga las elegidas con el flujo de playlist que ya existe: carpeta propia, resumen al terminar y "Reintentar" en las fallidas. Las que ya están en la biblioteca se saltan.

## 6. Errores

| Caso | Mensaje |
|---|---|
| Enlace privado, borrado o mal escrito | "No se pudo leer el enlace" |
| Spotify o Apple Music cambian su web | "Spotify ha cambiado; actualiza la app" (o "Apple Music…"), con el detalle en el log |
| Sin conexión | El aviso que ya existe: "Sin conexión" |
| Fragmento que no se puede bajar o analizar | La fila muestra "—" y las demás siguen |
| Pista Go+ de SoundCloud | "Solo vista previa" (sin botón de descarga) |
| Playlist de Spotify de más de 100 canciones | Se importan las que da la página y la hoja avisa: "Spotify solo muestra las primeras 100" |

## 7. Pruebas

- **Motor (pytest)**, con fixtures reales capturadas una vez y recortadas:
  - `ytm_watch_radio.json`, `ytm_moods.json`, `ytm_mood_playlists.json`;
  - `spotify_embed_playlist.html`, `spotify_embed_track.html`;
  - `apple_playlist.html`;
  - `sc_search.json`, `sc_set.json`.
- **Qué se prueba:**
  - `parse_link` con todas las formas de URL, incluidas las de `intl-es`, `?si=` y `spotify.link`, que redirige.
  - Los lectores de Spotify, Apple Music y SoundCloud, y su fallo con `source_changed` cuando falta el JSON.
  - `match`, con una tabla de casos: remix frente a original, "feat.", duración distinta y sin resultados.
  - `fit`, contando el doble y la mitad del BPM.
  - El trabajo `quick_analysis` con un descargador de fragmentos falso: caché, eventos, fallo y cancelación.
  - Las rutas nuevas.
- **UI (Vitest):**
  - pantalla Descubrir: pestañas, filas que se rellenan con los eventos, orden por encaje;
  - pestaña SoundCloud;
  - hoja Importar: estados, alternativas y "Descargar todas".
- **E2E** (motor falso con fakes para las recomendaciones, SoundCloud y los enlaces):
  - de una pista de la biblioteca, "Parecidas", la lista con distintivos, y descargar una;
  - pegar un enlace de Spotify, importar y ver la playlist en la biblioteca.
- **Banco:** `docs/bench/2026-11-fase5a-descubrir.md`, con 3 playlists reales de Spotify (aciertos del emparejado) y 3 canciones semilla (recomendaciones con datos y tiempo).

## 8. Criterios de aceptación

1. Las cifras de éxito de §1 se cumplen en el banco.
2. Moods y géneros funcionan con datos reales de YouTube Music.
3. La búsqueda y la descarga de SoundCloud funcionan, y las pistas Go+ se marcan.
4. Un enlace de Spotify, de Apple Music y de SoundCloud se importan a una playlist de la biblioteca.
5. Todas las pruebas pasan, y la UI se ve bien en el ancho de escritorio y a 375 px.

## 9. Riesgos

- **Spotify y Apple Music cambian su web sin aviso:** los lectores están aislados, con fixtures y un error claro. Si se rompen, solo hay que corregir el lector.
- **Las descargas parciales de yt-dlp (`--download-sections`) dependen de ffmpeg y del formato:** si fallan, se baja el audio completo de baja calidad (`-f worstaudio`) y se recorta.
- **Límites de YouTube:** muchas peticiones seguidas pueden dar errores temporales. Se usan concurrencia baja, caché permanente y reintento con espera.
- **Precisión del análisis de 60 s:** algo menor que la de la canción completa. Basta para filtrar y se marca como estimado; el análisis completo se hace al descargar.
