# OneForAll Fase 5a (Descubrir) — Plan de implementación

**Goal:** Ofrecer recomendaciones (parecidas a una canción, y por moods y géneros) con BPM y tonalidad calculados al vuelo, búsqueda y descarga en SoundCloud, e importación de enlaces de Spotify, Apple Music y SoundCloud a una playlist de la biblioteca.

**Architecture:**
- Paquete nuevo `engine/djengine/discover/`: `links`, `match`, `quick`, `fit` e `imports`.
- Todo lo que sale a la red pasa por `SearchService`, que gana `similar`, `moods`, `mood_playlists`, `soundcloud` y `read_link`. `FakeSearch` los imita, así el modo `--fake` y el E2E no tocan la red.
- Los resultados que llegan poco a poco (análisis rápido y emparejado) viajan como eventos `quick.result` y `match.result` por el WebSocket que ya existe, hacia un `discoverStore` nuevo en la UI.

**Tech Stack:** Python + FastAPI + ytmusicapi + yt-dlp + ffmpeg (sin dependencias nuevas; el HTML se lee con `urllib` y `json`). React + Zustand + Vitest. Playwright Electron.

**Spec:** `docs/diseno/specs/2026-11-10-oneforall-fase5a-descubrir-design.md`

## Global Constraints

- No hay dependencias nuevas de Python ni de npm.
- **Textos de la UI exactos:**
  - Descubrir, Parecidas a…, Moods y géneros, Parecidas
  - Encaja, Cerca, analizando…
  - Orden de YouTube, Mejor encaje
  - SoundCloud, Solo vista previa
  - Importar, Revisar, No encontrada, Ninguna, Descargar todas (n)
- **Errores exactos:**
  - "No se pudo leer el enlace"
  - "Spotify ha cambiado; actualiza la app"
  - "Apple Music ha cambiado; actualiza la app"
  - "Spotify solo muestra las primeras 100"
- **Números de la spec:**
  - Fragmento de 60 s desde el 30 % de la duración.
  - Concurrencia: 2 para el análisis rápido y 4 para el emparejado.
  - Encaje: BPM a ±6 %, contando también el doble y la mitad.
  - Puntuación del emparejado: `0.6·título + 0.3·artista + 0.1·duración`, con umbrales `found` ≥ 0,8 y `review` ≥ 0,5. La duración puntúa 1 si difiere ≤ 5 s y 0 si difiere más de 15 s.
  - Un análisis fallido se reintenta pasadas 24 h.
  - `scsearch25`.
- Los IDs de SoundCloud se guardan como `video_id = "sc:<id>"`.
- La UI se comprueba en el ancho de escritorio y a 375 px.
- No se hace push.

## Review Focus

1. **Enlaces con parámetros de seguimiento o formato raro** (`?si=…`, `intl-es/`, `spotify:` URI, `spotify.link/xyz` que redirige): todos deben reconocerse. Prueba en la Tarea 1.
2. **Una canción de Spotify con varios artistas o "feat." en el título** debe emparejarse como `found`. Las versiones "Remix" o "Live" no deben ganar a la original salvo que la original diga lo mismo. Prueba en la Tarea 2.
3. **Salir de la pantalla Descubrir** mientras se analiza: el trabajo se cancela, y al volver lo ya analizado sale de la caché sin repetir el análisis. Prueba en las Tareas 5 y 7.
4. **Una pista de la biblioteca sin `video_id`** (archivo propio) en "Parecidas a…": usa como semilla la primera coincidencia de "artista título" en YouTube Music. Si no hay ninguna, lista vacía con el aviso "No se encontraron recomendaciones". Prueba en la Tarea 4.
5. **Importar una lista en la que algunas canciones ya están en la biblioteca:** se saltan y el resumen las cuenta. Una lista de 0 canciones elegidas no crea una playlist vacía. Prueba en la Tarea 6.

---

### Task 1: Leer enlaces (Spotify, Apple Music, SoundCloud)

**Files:**
- Create: `engine/djengine/discover/__init__.py`, `engine/djengine/discover/links.py`
- Create fixtures (capturadas una vez de páginas públicas reales y recortadas a 3–5 canciones): `engine/tests/discover/fixtures/spotify_embed_playlist.html`, `spotify_embed_track.html`, `apple_playlist.html`, `sc_set.json`
- Test: `engine/tests/discover/test_links.py`

**Interfaces:**
- Produces:
  - `ImportItem` (pydantic): `title: str, artist: str, duration_s: int | None, url: str | None = None` (`url` solo para SoundCloud).
  - `ImportList` (pydantic): `name: str, service: Literal["spotify", "apple", "soundcloud"], items: list[ImportItem], truncated: bool = False`.
  - `parse_link(text: str) -> Link | None`, con `Link = {service, kind: "track" | "album" | "playlist", id: str, url: str}` (dataclass).
  - `read_spotify(link, fetch=_get) -> ImportList`, `read_apple(link, fetch=_get) -> ImportList`, `read_soundcloud(link, run=_ytdlp_json) -> ImportList`.
  - `read_link(link) -> ImportList`, que elige el lector según el servicio.
  - `_get(url) -> str` hace GET con `urllib` y un User-Agent de navegador, con un tiempo límite de 20 s. Sigue las redirecciones, también para `spotify.link`.

- [ ] **Step 1: Capturar las fixtures.** Hay que guardar el HTML real de una playlist pública de Spotify (`open.spotify.com/embed/playlist/<id>`) y de una canción, de una playlist pública de Apple Music, y la salida de `yt-dlp --flat-playlist -J <set de SoundCloud>`. Se recortan los arrays a 3–5 canciones, sin tocar la estructura, y se apunta la URL de origen en un comentario del test.
- [ ] **Step 2: Tests**

```python
@pytest.mark.parametrize("text,service,kind,id_", [
    ("https://open.spotify.com/playlist/37i9dQZF1DX0XUsuxWHRQd?si=abc", "spotify", "playlist", "37i9dQZF1DX0XUsuxWHRQd"),
    ("https://open.spotify.com/intl-es/track/4uLU6hMCjMI75M1A2tKUQC", "spotify", "track", "4uLU6hMCjMI75M1A2tKUQC"),
    ("spotify:album:1DFixLWuPkv3KT3TnV35m3", "spotify", "album", "1DFixLWuPkv3KT3TnV35m3"),
    ("https://music.apple.com/es/playlist/x/pl.u-abc", "apple", "playlist", "pl.u-abc"),
    ("https://music.apple.com/es/album/y/123?i=456", "apple", "track", "456"),
    ("https://soundcloud.com/artist/sets/name", "soundcloud", "playlist", "artist/sets/name"),
    ("https://soundcloud.com/artist/track-name", "soundcloud", "track", "artist/track-name"),
])
def test_parse_link(text, service, kind, id_): ...

def test_parse_link_ignores_youtube_and_text():
    assert parse_link("https://youtu.be/abc") is None and parse_link("la graciosa") is None

def test_spotify_link_shortener_is_followed(monkeypatch): ...  # spotify.link/x → _get devuelve la URL final → Link de playlist

def test_read_spotify_playlist_fixture():
    lst = read_spotify(parse_link(PL_URL), fetch=lambda u: FIX("spotify_embed_playlist.html"))
    assert lst.service == "spotify" and lst.name and len(lst.items) >= 3
    assert all(i.title and i.artist and i.duration_s for i in lst.items)

def test_read_spotify_track_fixture(): ...      # una sola canción
def test_read_apple_playlist_fixture(): ...     # nombre + canciones con duración
def test_read_soundcloud_set(): ...             # items con url, sin necesidad de emparejar

@pytest.mark.parametrize("reader,msg", [(read_spotify, "Spotify ha cambiado; actualiza la app"),
                                        (read_apple, "Apple Music ha cambiado; actualiza la app")])
def test_changed_page_is_a_clear_error(reader, msg): ...  # "<html></html>" → UserError("source_changed", msg)

def test_unreachable_link_is_a_clear_error(): ...         # fetch lanza HTTPError 404 → UserError("bad_link", "No se pudo leer el enlace")

def test_spotify_over_100_is_flagged(): ...               # fixture con 100 canciones + total 140 → truncated=True
```

- [ ] **Step 3:** Ejecutar `cd engine && .venv/Scripts/python -m pytest tests/discover/test_links.py -q`. Resultado esperado: FAIL.
- [ ] **Step 4: Implementar.**
  - **Spotify:** lee `__NEXT_DATA__`, luego `props.pageProps.state.data.entity`, con `name` y `trackList[]` (`title`, `subtitle` = artistas separados por comas y `duration` en ms). `truncated` vale `len(trackList) < entity.trackCount` (si existe la clave). Si la canción es suelta, `entity` es la canción.
  - **Apple Music:** lee `serialized-server-data`, luego `data[0].data.sections[]`. Los elementos de la sección de canciones traen `title`, `artistName` y `duration` en ms. El nombre sale de `headerSection`.
  - Si la ruta exacta difiere de la fixture real, se ajusta a la fixture y el lector busca el array de canciones de forma defensiva.
- [ ] **Step 5:** Ejecutar el test (PASS) y hacer commit: `feat(discover): read Spotify, Apple Music and SoundCloud links`.

### Task 2: Emparejado con YouTube Music

**Files:**
- Create: `engine/djengine/discover/match.py`
- Modify: `engine/djengine/server.py` (cuerpo `ImportMatchJobBody`, concurrencia `"import_match": 1`)
- Test: `engine/tests/discover/test_match.py`

**Interfaces:**
- Consumes: `ImportItem` (Tarea 1), `SearchService.search(q, "songs")`, `normalize_key` (de `library.py`).
- Produces:
  - `score(item: ImportItem, cand: SearchResult) -> float`.
  - `match(search, item) -> MatchResult`, donde `MatchResult` (pydantic) tiene `status: Literal["found", "review", "missing"], best: SearchResult | None, alternatives: list[SearchResult]` (como mucho 3, sin `best`).
  - Trabajo `import_match` con `{items: [ImportItem]}`: emite `{"type": "match.result", "job_id", "index": int, "result": MatchResult}` por cada canción, con 4 a la vez (`asyncio.Semaphore(4)` y `to_thread`). El resultado final es `{"results": [MatchResult]}`.

- [ ] **Step 1: Tests** (con un `search` falso que devuelve candidatas fijas):

```python
def test_exact_is_found(): ...            # mismo título, artista y duración → found, score ≥ 0.8
def test_feat_and_multiple_artists_found(): ...   # "Song (feat. B)" / "A, B" frente a "Song" / "A" → found
def test_remix_does_not_beat_original():  # candidatas [Song (Remix) 240 s, Song 200 s], item Song 200 s → best = original
    ...
def test_remix_requested_picks_remix(): ...       # item "Song - Remix" → best = el remix
def test_duration_far_off_goes_to_review(): ...   # título y artista iguales, ±30 s → review
def test_nothing_is_missing(): ...                # sin resultados → missing, best None
def test_alternatives_capped_at_3(): ...
async def test_import_match_job_emits_one_event_per_item(svc): ...  # 5 items → 5 eventos match.result con index 0..4
```

- [ ] **Step 2:** Ejecutar el test (FAIL), implementar y ejecutar otra vez (PASS).
  - El título se normaliza con `normalize_key`, que ya quita "feat." y "(Official Video)".
  - Para que un remix o un live no gane a la original, si en la candidata aparece "remix", "live", "en vivo", "acoustic" o "sped up" y en el título original no, el parecido del título se multiplica por 0,6.
- [ ] **Step 3: Commit**: `feat(discover): match imported songs to YouTube Music`.

### Task 3: SoundCloud en el buscador

**Files:**
- Modify: `engine/djengine/search.py` (`Kind` y `SearchKind` ganan `"soundcloud"`; métodos `soundcloud(q)` y `read_link(link)`), `engine/djengine/fakes.py` (`FakeSearch.soundcloud` y `FakeSearch.read_link`), `engine/djengine/pipelines.py` (el `video_id` de SoundCloud), `engine/djengine/server.py` (`/search?kind=soundcloud`)
- Create fixture: `engine/tests/discover/fixtures/sc_search.json` (salida real de `yt-dlp --flat-playlist -J "scsearch5:quevedo"`, incluida una pista Go+ si sale; si no, se añade una a mano con `duration: 30`)
- Test: `engine/tests/discover/test_soundcloud.py`

**Interfaces:**
- Produces:
  - `SearchResult` gana `source: Literal["youtube", "soundcloud"] = "youtube"` y `preview_only: bool = False`.
  - `SearchService.soundcloud(q) -> list[SearchResult]` devuelve `kind="soundcloud"`, `id="sc:<id>"`, `url`, `duration_s`, el uploader como `artist` y `preview_only` (duración ≤ 31 s, o `entry.get("availability") == "premium_only"`). Las pistas de menos de 60 s se quitan, salvo las `preview_only`, que se quedan para que se vean marcadas.
  - La descarga de un objetivo de SoundCloud guarda `video_id=t.id` (con el prefijo `sc:`).

- [ ] **Step 1: Tests**:
  - Parseo de la fixture: ids con `sc:`, `source="soundcloud"` y la pista Go+ con `preview_only`.
  - `/search?kind=soundcloud` responde 200 con el fake.
  - Una descarga desde un resultado de SoundCloud (motor falso) añade la pista con `video_id == "sc:123"`.
  - Una segunda búsqueda marca `in_library=True`.
  - `POST /jobs` de descarga con un objetivo `preview_only` da 422 con "Solo vista previa".
- [ ] **Step 2:** Ejecutar (FAIL), implementar y ejecutar (PASS).
- [ ] **Step 3: Commit**: `feat(search): SoundCloud search and download`.

### Task 4: Recomendaciones (parecidas, moods y géneros)

**Files:**
- Create: `engine/djengine/discover/recs.py`
- Modify: `engine/djengine/search.py` (`similar`, `moods`, `mood_playlists`), `engine/djengine/fakes.py`, `engine/djengine/server.py` (rutas)
- Create fixtures: `ytm_watch_radio.json`, `ytm_moods.json`, `ytm_mood_playlists.json` (capturadas con ytmusicapi y recortadas)
- Test: `engine/tests/discover/test_recs.py`

**Interfaces:**
- Produces:
  - `SearchService.similar(video_id) -> list[SearchResult]` usa `get_watch_playlist(videoId, radio=True, limit=30)`. Quita la propia canción y los duplicados, y aplica `filter_results`.
  - `SearchService.moods() -> list[MoodSection]`, con `MoodSection = {title, items: [{title, params}]}`.
  - `SearchService.mood_playlists(params) -> list[SearchResult]` (`kind="playlist"`).
  - `recs.seed_for_track(svc, track) -> str | None` devuelve el `video_id`; si falta, la primera canción de `search(f"{artist} {title}", "songs")`.
  - Rutas:
    - `GET /discover/similar?track_id=|video_id=` devuelve `{"seed": SearchResult | None, "items": [Rec]}`. `Rec` = `SearchResult` + `bpm: float | None, camelot: str | None, analysed: bool` (de la caché de la Tarea 5).
    - `GET /discover/moods`.
    - `GET /discover/mood?params=`, que devuelve playlists; sus canciones se cargan con el `/playlist/{id}` que ya existe.

- [ ] **Step 1: Tests**:
  - `similar` con la fixture: sin la semilla, sin duplicados y con ≥ 20 elementos en la fixture completa.
  - Una pista sin `video_id` usa la búsqueda como semilla.
  - Sin resultados de búsqueda, `{"seed": None, "items": []}`.
  - Parseo de `moods` y `mood_playlists`.
  - Las rutas devuelven 200 con el fake.
  - `track_id` desconocido da 404.
- [ ] **Step 2:** Ejecutar (FAIL), implementar y ejecutar (PASS). Hacer commit: `feat(discover): similar songs and YouTube Music moods`.

### Task 5: Análisis rápido de 60 s y encaje

**Files:**
- Create: `engine/djengine/discover/quick.py`, `engine/djengine/discover/fit.py`
- Modify: `engine/djengine/library.py` (tabla `quick_analysis` en `_SCHEMA`), `engine/djengine/server.py` (`Services.clip_downloader`, cuerpo `QuickAnalysisJobBody`, concurrencia `"quick_analysis": 1`, porque el trabajo lleva su propio semáforo de 2), `engine/djengine/fakes.py` (`fake_clip_downloader`)
- Test: `engine/tests/discover/test_quick.py`, `engine/tests/discover/test_fit.py`

**Interfaces:**
- Consumes: `decode`, `estimate_tempo` (`fold_bpm`, rango de Ajustes), `estimate_key` y `to_camelot`/`camelot_of`, que ya existen en `analysis/`.
- Produces:
  - `fit(ref_bpm: float | None, ref_camelot: str | None, bpm: float | None, camelot: str | None) -> Literal["encaja", "cerca"] | None`.
  - `download_clip(ctx, url, start_s: float, seconds: float = 60) -> Path`, la versión real: yt-dlp `-f bestaudio --download-sections "*{start}-{end}" --force-keyframes-at-cuts`. Si falla, `-f worstaudio` completo y recorte con ffmpeg.
  - `quick_analyse(path, lo, hi) -> {bpm, tonic, mode, camelot}`.
  - `QuickCache(db_path)`, con `get(video_id) -> dict | None` (sin los fallos de menos de 24 h) y `put(video_id, result | None)`.
  - Trabajo `quick_analysis` con `{video_ids: [str], durations: [int|None]}`:
    - Va de 2 en 2.
    - Se salta los que ya están en caché o en la biblioteca analizados (por `video_id` → pista → registro de análisis).
    - Emite `{"type": "quick.result", "video_id", "bpm", "camelot", "failed": bool}`.
    - Se puede cancelar entre pistas.
  - `fakes.fake_clip_downloader(ctx, url, start_s, seconds)` crea un tren de clics a 120 BPM, o a 128 BPM si el id acaba en "8". Si el id contiene "private", da `unavailable`.

- [ ] **Step 1: Tests**:

```python
@pytest.mark.parametrize("ref,cand,expected", [
    ((128, "8A"), (128, "8A"), "encaja"), ((128, "8A"), (64, "9A"), "encaja"), ((128, "8A"), (135, "8A"), "cerca"),
    ((128, "8A"), (128, "3B"), "cerca"), ((128, "8A"), (100, "3B"), None), ((None, None), (128, "8A"), None),
    ((128, None), (121, None), "cerca")])
def test_fit(ref, cand, expected): ...
```

  - Trabajo, con el descargador falso: emite un `quick.result` por id, con un BPM de 120 ± 1.
  - La caché impide que se descargue otra vez (contador).
  - Un fallo se guarda y no se reintenta antes de 24 h (reloj simulado con monkeypatch); a las 25 h, sí.
  - Una pista de la biblioteca ya analizada sale de su análisis sin descargar nada.
  - Cancelar en mitad del trabajo deja en caché las ya terminadas, y un trabajo nuevo con los mismos ids solo descarga las que faltan.
  - Las rutas: `POST /jobs {type: "quick_analysis"}` responde 200.
- [ ] **Step 2:** Ejecutar (FAIL), implementar y ejecutar (PASS). Hacer commit: `feat(discover): 60 s quick analysis with cache, and fit`.

### Task 6: Importar a una playlist de la biblioteca

**Files:**
- Modify: `engine/djengine/pipelines.py` (extraer el cuerpo del trabajo padre de `start_playlist` a `_run_playlist(svc, ctx, title, folder, targets, options, playlist_yt_id)` y añadir `start_import`), `engine/djengine/server.py` (rutas `POST /discover/link`, `POST /jobs {type: "import_match"}` de la Tarea 2 y `{type: "import"}`)
- Test: `engine/tests/discover/test_import.py`

**Interfaces:**
- Consumes: `read_link` (Tarea 1), `match` (Tarea 2) y la descarga de SoundCloud (Tarea 3).
- Produces:
  - `POST /discover/link {text}` devuelve `ImportList`, o 422 con `bad_link` o `source_changed`.
  - `start_import(svc, name: str, targets: list[SearchResult], options: ConvertOptions) -> Job`. Usa el mismo resultado de trabajo padre que `start_playlist` (`done`, `skipped`, `failed`, `cancelled`), crea la playlist en la biblioteca con `yt_id=None` y usa la carpeta `<music_dir>/<nombre>`.
  - Cuerpo `{type: "import", name, targets: [SearchResult] (min 1), options}`.

- [ ] **Step 1: Tests**:
  - `start_playlist` sigue pasando sus tests, que ya existen (refactor sin cambio de comportamiento).
  - Importar 3 objetivos del fake crea la playlist "Mi lista" con 3 pistas en `<music>/Mi lista/`.
  - Un objetivo que ya está en la biblioteca cuenta como `skipped`.
  - `targets: []` da 422 y no crea ninguna playlist.
  - `POST /discover/link` con un enlace de Spotify (fake `read_link`) devuelve los items.
  - Una página cambiada da 422 con el mensaje exacto.
- [ ] **Step 2:** Ejecutar (FAIL), implementar y ejecutar (PASS). Ejecutar la suite completa del motor. Hacer commit: `feat(discover): import a link into a library playlist`.

### Task 7: UI de Descubrir

**Files:**
- Create: `ui/src/stores/discoverStore.ts`, `ui/src/screens/DiscoverScreen.tsx`, `ui/src/screens/DiscoverScreen.test.tsx`, `ui/src/screens/discover.css`
- Modify:
  - `ui/src/lib/engine.tsx`: los eventos `quick.*` y `match.*` van a `discoverStore`.
  - `ui/src/lib/engineClient.ts`: `similar`, `moods`, `moodPlaylists`, `quickAnalysis`, `cancelJob` (si no existe).
  - `ui/src/lib/types.ts`: `Rec`, `MoodSection`, `Fit`, más `source` y `preview_only` en `SearchResult`.
  - `ui/src/components/AppShell.tsx`: entrada "Descubrir" con el icono `Compass`, después de Buscar.
  - `ui/src/stores/uiStore.ts`: ruta `descubrir` y `discoverSeed: TrackRecord | null`.
  - `ui/src/App.tsx`.
  - `ui/src/screens/LibraryScreen.tsx` y `ui/src/components/DataSheet.tsx`: botón "Parecidas".
  - `ui/src/lib/fit.ts`, el mismo `fit` que el motor, para recalcular en el cliente cuando cambia la referencia manual, con su test.

**Interfaces:**
- Consumes: las rutas de las Tareas 4 y 5.
- Produces:
  - `discoverStore`: `quick: Record<videoId, {bpm, camelot, failed} | 'pending'>`, `applyEvent(e)`, `reset()`.
  - Las filas reutilizan el componente de fila de resultado del buscador, con las columnas extra BPM, Tonalidad y el distintivo.

- [ ] **Step 1: Tests (Vitest)**:
  - "Parecidas a…" con una semilla carga `similar` y lanza `quickAnalysis` con los ids que no estén analizados.
  - Un evento `quick.result` rellena la fila (`128,0`, `8A`) y pone **Encaja** si la referencia es 128/8A.
  - Una fila pendiente muestra "analizando…" y una fallida, "—".
  - "Mejor encaje" ordena Encaja > Cerca > nada > pendiente.
  - En "Moods y géneros", una ficha → playlists → canciones. La referencia manual (BPM 95, 8A) recalcula los distintivos sin llamar al motor.
  - **Desmontar la pantalla cancela el trabajo de análisis** (`cancelJob` llamado). Al volver, las filas ya analizadas salen del store sin nuevas peticiones para esos ids.
  - Una semilla sin recomendaciones muestra "No se encontraron recomendaciones".
  - `fit.test.ts` usa la misma tabla que la Tarea 5.
- [ ] **Step 2:** Ejecutar (FAIL), implementar y ejecutar `npx vitest run` (PASS). Comprobar en el navegador (capturas E2E de la Tarea 9) a 375 px y en el ancho de escritorio.
- [ ] **Step 3: Commit**: `feat(ui): Descubrir screen with live BPM/key and fit`.

### Task 8: UI de SoundCloud e Importar

**Files:**
- Create: `ui/src/components/ImportSheet.tsx`, `ui/src/components/ImportSheet.test.tsx`
- Modify:
  - `ui/src/screens/SearchScreen.tsx`: pestaña SoundCloud. Al pulsar Enter con un enlace de Spotify, Apple Music o SoundCloud se llama a `discoverLink` y se abre la hoja.
  - `ui/src/lib/engineClient.ts`: `discoverLink`, `importMatch`, `startImport`.
  - `ui/src/stores/uiStore.ts`: `importList: ImportList | null`.
  - `ui/src/App.tsx`.
  - Los tests del buscador que ya existen.

**Interfaces:**
- Produces: `ImportSheet({ list, onClose })`.

- [ ] **Step 1: Tests (Vitest)**:
  - **Buscador:**
    - La pestaña SoundCloud busca con `kind=soundcloud`.
    - Una fila `preview_only` muestra "Solo vista previa" y no tiene botón de descarga.
    - Pegar un enlace de Spotify y pulsar Enter llama a `discoverLink` y abre la hoja. Si falla, toast con el mensaje exacto.
  - **Hoja:**
    - Muestra el nombre y el servicio, lanza `importMatch` y los eventos rellenan las filas (✓, Revisar con selector, No encontrada).
    - Elegir "Ninguna" la quita.
    - **Descargar todas (n)** cuenta solo las elegidas y llama a `startImport(name, targets, options)`.
    - Con `truncated`, aviso "Spotify solo muestra las primeras 100".
    - Una lista de SoundCloud no se empareja: todas salen ✓ con su URL.
- [ ] **Step 2:** Ejecutar (FAIL), implementar y ejecutar (PASS). Hacer commit: `feat(ui): SoundCloud tab and Importar sheet`.

### Task 9: E2E, banco y resumen

**Files:**
- Modify: `e2e/app.spec.ts`
- Create: `engine/bench/discover_bench.py`, `docs/bench/2026-11-fase5a-descubrir.md`, `docs/diseno/fase5a-resumen.md`

- [ ] **Step 1: E2E** (motor falso):
  - Descargar una canción, luego Biblioteca → "Parecidas": salen filas con BPM y algún "Encaja". Capturas a 1280 y 375 px, y descargar una.
  - Pegar un enlace de Spotify (fake) en el buscador abre la hoja Importar. "Descargar todas" hace que aparezca la playlist en la biblioteca.
  - Pestaña SoundCloud: un resultado con "Solo vista previa".
- [ ] **Step 2:** Ejecutar todas las suites (pytest, Vitest y Playwright). Todo debe pasar. Reinstalar el motor en `build/runtime` y ejecutar `npm run dist`.
- [ ] **Step 3: Banco real (`discover_bench.py`)**:
  - 3 playlists públicas de Spotify: cuántas salen `found`, `review` y `missing`, y revisar a mano 10 `found` de cada una.
  - 3 semillas de la biblioteca: cuántas recomendaciones, cuántas con datos y en cuánto tiempo.
  - Apuntarlo en `docs/bench/2026-11-fase5a-descubrir.md` frente a los objetivos de §1 de la spec.
- [ ] **Step 4:** Escribir el resumen y hacer commit: `docs: phase 5a summary and bench`.
