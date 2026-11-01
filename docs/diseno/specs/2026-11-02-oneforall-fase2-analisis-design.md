# OneForAll — Fase 2: Análisis DJ — Especificación

- Fecha: 2026-11-02
- Estado: pendiente de revisión
- Base: `docs/diseno/specs/2026-11-01-dj-app-design.md` (Fase 1, ya en `main`)
- Referencia: [stemdeck](https://github.com/stemdeckapp/stemdeck) (Apache-2.0). Usa librosa para BPM y tonalidad y pyloudnorm para el loudness. Si se reutiliza código, se conserva su aviso de licencia.

## 1. Objetivo

Cada pista (de la biblioteca o un archivo propio) obtiene BPM, tonalidad, loudness, forma de onda y rejilla de beats fiables. Esos datos se ven en la app, se escriben en las etiquetas que leen Rekordbox, Serato, VirtualDJ y Traktor, y alimentan un buscador de mezcla armónica.

Éxito = precisión medida en GiantSteps (§6) igual o mejor que el umbral fijado, y los bugs de `review.txt` sobre tempo y tonalidad incorrectos o el análisis en playlists, resueltos.

## 2. Decisiones

| Tema | Decisión |
|---|---|
| Librerías | essentia y madmom no se instalan con pip en Windows + Python 3.12 (comprobado). Candidatas de tempo: **librosa** y **deeprhythm** (CNN, PyTorch). Candidatas de tonalidad: **librosa + perfiles** (`edma`, `temperley`, `krumhansl`) y la **CNN de tonalidad de madmom** (Korzeniowski & Widmer), necesaria para optar a 0,80 MIREX. |
| Método | Todas tras una misma interfaz. El banco GiantSteps elige el ganador **por separado para tempo y para tonalidad**. |
| Licencia del modelo de tonalidad | Los pesos de madmom son CC BY-NC-SA (no comercial): válido para el uso personal del dueño. Si algún día la app se vende, hay que sustituir ese modelo. Se anota en el README y en Ajustes → Acerca de. |
| Rejilla de beats | Siempre de librosa (`beat_track`), alineada al BPM ganador. |
| Referencia de precisión | Dataset público GiantSteps (tempo y tonalidad). Solo se descarga en local para el banco, nunca va en el instalador. |
| Notación en etiquetas | Ajuste: **Camelot (por defecto)** o musical. En la app se muestran siempre las dos: «8A · Lam». |
| Analizar al descargar | Ajuste, activado por defecto. Incluye playlists. |
| Fuera de alcance | Edición de la rejilla y detección de secciones (Fase 4); mezclador (Fase 3). BPM y tonalidad en resultados de búsqueda de pistas que no tienes (no hay audio que analizar). |

## 3. Motor

### 3.1 Módulos (`engine/djengine/analysis/`)

| Módulo | Interfaz | Notas |
|---|---|---|
| `audio_io.py` | `decode(path, sr) -> np.ndarray` (mono float32) | Decodifica con ffmpeg por pipe, sin audioread. |
| `tempo.py` | `estimate_tempo(y, sr, method) -> TempoResult(bpm, confidence, beats: list[float])` | Métodos `librosa` y `deeprhythm`. Plegado al rango DJ configurable (por defecto 70–180): duplica o divide por 2 hasta entrar. Precisión de 0,1 BPM. |
| `key.py` | `estimate_key(y, sr, method) -> KeyResult(tonic, mode, camelot, confidence)` | Métodos: `edma`, `temperley`, `krumhansl` (`chroma_cqt` sumado en toda la pista, correlado con los 24 perfiles rotados) y `cnn` (modelo de madmom). |
| `key_cnn.py` | `CnnKey.predict(path) -> KeyResult` | Inferencia de la CNN de madmom. Primera opción: madmom compilado desde el código fuente (git) dentro del runtime. Si no compila, se reimplementa su preprocesado (espectrograma logarítmico filtrado) y la inferencia en numpy con los pesos originales, verificando que da las mismas salidas que madmom en Linux/WSL o en fixtures de referencia. |
| `loudness.py` | `measure(y_stereo, sr) -> (lufs, peak_db)` | pyloudnorm (ITU-R BS.1770). |
| `waveform.py` | `compute(y, sr, buckets=2000) -> {peaks: [max…], low: […], mid: […], high: […]}` | Valores normalizados 0–1 por bucket. Bandas: <250 Hz, 250 Hz–4 kHz, >4 kHz. |
| `camelot.py` | `to_camelot(tonic, mode)`, `to_musical(code, lang)`, `compatible(a, b) -> Level \| None` | Niveles: `same` (misma clave), `adjacent` (±1 con la misma letra), `relative` (mismo número con la otra letra). |
| `runner.py` | `make_analysis_runner(svc, path, track_id=None) -> Runner` | Etapas: `decoding`, `tempo`, `key`, `loudness`, `waveform`, `saving`. Llama a `check_cancelled()` entre etapas. |

`ANALYSIS_VERSION = 1`: se guarda con cada resultado. Si sube, la app ofrece reanalizar.

### 3.2 Datos

- Nueva tabla `analyses(path TEXT PK, size INTEGER, mtime REAL, bpm REAL, bpm_confidence REAL, bpm_source TEXT, tonic TEXT, mode TEXT, camelot TEXT, key_confidence REAL, lufs REAL, peak_db REAL, version INTEGER, created_at TEXT)`.
  - `bpm_source`: `auto` o `manual`.
  - Un resultado vale mientras coincidan ruta, tamaño y mtime.
- JSON aparte `data/analysis/<sha1(path)>.json` con `beats` y `waveform` (no caben bien en SQLite).
- Para pistas de la biblioteca también se rellenan `tracks.bpm`, `musical_key` y `camelot`, y se añaden columnas `lufs REAL`, `analyzed_at TEXT` (migración `ALTER TABLE` idempotente al arrancar).
- **Etiquetas:** `TBPM` (entero redondeado, el estándar que leen todos) y `TKEY` según el ajuste de notación (Camelot `8A` o musical `Am`). MP4: `tmpo` + `initialkey`. Vorbis: `BPM` + `INITIALKEY`.

### 3.3 Trabajos y API

- Tipo de trabajo `analysis`, concurrencia 2. Cancelable por proceso como el resto.
- **Analizar al descargar:** al terminar con éxito un trabajo `download` (suelto o hijo de playlist), se encola un `analysis` independiente. Fallar o cancelar el análisis nunca afecta a la descarga.
- **BPM manual:** `PUT /analysis/bpm {path, bpm}` → `bpm_source = manual`, escribe la etiqueta. Un reanálisis conserva el BPM manual salvo que se pida `{"reset_bpm": true}`.

| Método | Ruta | Uso |
|---|---|---|
| POST | `/jobs` `{"type":"analysis","paths":[...],"force":false}` | Analizar archivos (con `force` se ignora la caché) |
| GET | `/analysis?path=` | Resultado cacheado + JSON de beats y forma de onda, o 404 |
| PUT | `/analysis/bpm` | BPM manual |
| GET | `/harmonic?ref_track=&bpm=&camelot=&bpm_tolerance=6` | Pistas compatibles de la biblioteca, con nivel y diferencia de BPM |
| GET | `/audio?path=&token=` | Sirve el audio con soporte de rangos. Solo extensiones de audio, y solo rutas de la biblioteca, de `analyses` o elegidas por el usuario en la sesión |

### 3.4 Errores

- Archivo ilegible o corrupto → `UserError("unreadable", "No se puede leer el audio de este archivo")`.
- Pista de menos de 10 s → se analiza, pero BPM y tonalidad se marcan con confianza baja.
- Si deeprhythm (PyTorch) no carga, el motor vuelve a librosa y lo registra en el log.

## 4. Interfaz

- **Biblioteca:**
  - Columnas BPM, Tonalidad y LUFS. La tonalidad es una etiqueta Camelot coloreada con el tono de su posición en la rueda (12 colores con contraste ≥ 4,5:1).
  - Acciones "Analizar" por fila y "Analizar seleccionadas".
  - "Analizar archivo…" en la barra de herramientas (selector), y arrastrar audio sobre la ventana abre el análisis de ese archivo.
- **Historial:** columnas BPM y Tonalidad cuando la pista está analizada.
- **Ventana de datos** (GlassSheet ancho), que se abre al hacer doble clic en una fila de la biblioteca o el historial, desde "Datos" en una descarga terminada y al analizar un archivo propio:
  - Forma de onda en canvas: color por bandas, marcas de beat, cursor de reproducción, clic para saltar.
  - Reproducir y pausar, con el audio servido por `/audio`.
  - Datos: BPM (con indicador de confianza baja si < 0,5, y "manual" si aplica), tonalidad «8A · Lam», LUFS, pico, duración, formato, bitrate y frecuencia de muestreo.
  - **Tap tempo:** botón o tecla espacio. BPM = 60 / media de los últimos 8 intervalos. Se reinicia tras 2 s sin pulsar. Necesita al menos 4 pulsaciones. "Aplicar" guarda el BPM manual.
  - Botones "Reanalizar" y "Mostrar en carpeta".
  - Mientras se analiza: progreso por etapa y botón Cancelar. Al cancelar no queda resultado parcial.
- **Pantalla "Armonía"** (nueva entrada en la barra lateral):
  - Referencia: elegir una pista de la biblioteca o introducir BPM y Camelot.
  - Margen de BPM (±2, 4, 6, 8 %), contando también el doble y la mitad.
  - Resultados ordenados por nivel (`same` > `adjacent` > `relative`) y después por diferencia de BPM. Cada uno con la etiqueta «Misma clave» / «±1» / «Relativa» y la diferencia «+1,2 %».
- **Ajustes:** "Analizar al descargar" (interruptor), "Notación de tonalidad en etiquetas" (Camelot / Musical), "Rango de BPM" (mínimo y máximo, por defecto 70–180).

## 5. Pruebas

- **Unitarias del motor (audio sintético generado en el test):**
  - Clics a 128 BPM → 128 ± 0,5; a 64 BPM → plegado a 128; a 174 BPM → 174.
  - Progresión de acordes en La menor → `A minor` / `8A`; en Do mayor → `8B`.
  - Tono a −20 dBFS → LUFS esperado ± 0,5.
  - Forma de onda: el silencio da ceros y un tono grave carga la banda `low`.
  - Rueda Camelot completa (24 claves) y matriz de compatibilidad.
  - Caché: el mismo archivo sin cambios no se reanaliza; si cambia el mtime, sí.
  - BPM manual conservado al reanalizar.
  - Analizar al descargar encola el análisis también en hijos de playlist (bug de `review.txt`).
  - Cancelar en mitad de un análisis no deja fila en `analyses` ni JSON.
  - `/audio` rechaza rutas fuera de lo permitido y extensiones que no son de audio.
- **UI (Vitest):** matemática del tap tempo, orden y etiquetas de Armonía, columnas nuevas, ventana de datos con un resultado simulado.
- **E2E:** descargar (motor fake) → análisis automático → abrir la ventana de datos → BPM y tonalidad visibles.
- **Banco (`engine/bench/`, `pytest -m bench`, fuera de la ejecución normal):** ver §6.

## 6. Banco de precisión (GiantSteps)

- Script `engine/bench/fetch_giantsteps.py`: descarga anotaciones y audio (fragmentos de 2 min) de los datasets *GiantSteps Key* y *GiantSteps Tempo* a `engine/bench/data/` (ignorado por git). Informa de cuántas pistas se pudieron bajar.
- Script `engine/bench/run.py`: ejecuta cada combinación (tempo: `librosa`, `deeprhythm`; tonalidad: `edma`, `temperley`, `krumhansl`) y escribe `docs/bench/2026-11-fase2.md` con:
  - Tempo: **Accuracy1** (±4 %) y **Accuracy2** (±4 % admitiendo ×2, ×½, ×3, ×⅓).
  - Tonalidad: **MIREX weighted score** (exacta 1, quinta 0,5, relativa 0,3, paralela 0,2) y acierto exacto.
  - Tiempo medio por pista.
- **Elección:** gana el mejor Accuracy2 en tempo (desempate con Accuracy1) y el mejor MIREX en tonalidad. En empate (< 1 punto), el más rápido. El ganador queda fijado como valor por defecto en `analysis/config.py`.
- **Umbrales de aceptación** (fijados con el dueño a partir del estado del arte publicado en GiantSteps):
  - **Tempo: Accuracy2 ≥ 90 %.** Es la medida útil para un DJ: la app ya pliega 64 a 128 con el rango 70–180. Accuracy1 se informa siempre; un 90 % exacto queda por encima de lo publicado, en parte por errores en las propias anotaciones del dataset.
  - **Tonalidad: MIREX ≥ 0,80.** Está en el límite de lo mejor publicado. Si ningún candidato llega, se presenta el mejor resultado y el dueño decide antes de cerrar la fase.
- **Notas de tempo:** se usan las anotaciones de tempo revisadas de GiantSteps cuando estén disponibles.
- Si con deeprhythm gana el tempo, PyTorch (CPU) entra en el runtime ya en esta fase (unos 250 MB más en el instalador; la Fase 3 lo necesitaría de todos modos).

## 7. Criterios de aceptación

1. Con "Analizar al descargar" activo, una descarga y una playlist de 3 pistas acaban con BPM y tonalidad en la biblioteca y en las etiquetas `TBPM` y `TKEY` (Camelot).
2. Cambiar la notación a Musical hace que los análisis siguientes escriban `Am`.
3. "Analizar archivo…" sobre un archivo que no está en la biblioteca muestra la ventana de datos con forma de onda, beats, BPM, tonalidad y LUFS, y se puede reproducir.
4. El tap tempo con 8 pulsaciones a 120 BPM muestra 120,0 ± 0,5; "Aplicar" guarda el BPM y un reanálisis lo conserva.
5. Armonía, con una pista 8A a 128 BPM como referencia, lista primero las 8A en 120–136 BPM, luego 7A y 9A, y luego 8B.
6. Cancelar un análisis no deja resultado ni JSON, y no afecta a otros trabajos.
7. El informe del banco existe en `docs/bench/` y el método elegido cumple los umbrales de §6: tempo Accuracy2 ≥ 90 % y tonalidad MIREX ≥ 0,80 (o hay una decisión documentada del dueño sobre la tonalidad).

## 8. Riesgos

- **Audio de GiantSteps:** sale de URLs de vista previa que pueden haber caducado → se mide con lo disponible y se indica el tamaño de la muestra.
- **Tonalidad en música urbana:** GiantSteps es solo electrónica → la precisión en reggaetón y urbano puede ser menor. Se documenta; el dueño puede validar con su colección más adelante.
- **Peso de PyTorch** si gana deeprhythm (ver §6).
- **CNN de tonalidad:** compilar madmom en Windows puede fallar → plan B con reimplementación en numpy (más trabajo, verificable con salidas de referencia).
- **Música urbana sin Rekordbox:** se validará más adelante con una referencia propia (unas 30 canciones con BPM y tonalidad contrastados en fuentes públicas como Tunebat o SongBPM).
