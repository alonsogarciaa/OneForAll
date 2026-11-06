# OneForAll — Fase 4a: Herramientas DJ — Especificación

- Fecha: 2026-11-06
- Estado: aprobada (2026-11-06)
- Base: `docs/diseno/specs/2026-11-01-dj-app-design.md` (§8, hoja de ruta) y las Fases 2, 3a y 3b (en `main`).
- La Fase 4 se divide en **4a (preparación DJ, esta spec)** y **4b (mejora de audio con IA, y exportar vídeo con la imagen original)**. Lo decidió el dueño el 2026-11-06.

## 1. Objetivo

Dejar cada canción lista para pinchar:

- rejilla de beats correcta y editable;
- secciones marcadas (Intro, Subida, Estribillo/Drop, Bajón, Outro);
- versiones del archivo a otro BPM o tonalidad, sin tocar el original;
- todo exportado a Rekordbox, VirtualDJ y Serato, con BPM, tonalidad, rejilla y cues.

Cubre la petición de `review.txt` "ventana de cambiador de bpm y de tono".

Éxito:

- la rejilla y las secciones caen en el compás correcto en reguetón y música urbana;
- el archivo con otro BPM o tono suena limpio, como la exportación del mezclador;
- el dueño importa la exportación en su programa DJ y ve BPM, tonalidad, rejilla y cues en su sitio.

## 2. Decisiones

| Tema | Decisión |
|---|---|
| Modelo de rejilla | **Rejilla fija: ancla (el primer "1") + BPM**, como los programas DJ. La lista de golpes que ya existe se calcula a partir de ella. Fuera de alcance: rejillas con cambios de tempo. |
| Secciones | Cortes donde cambia la canción, ajustados a frases de 8 compases sobre la rejilla, con nombre por energía: Intro, Subida, Estribillo/Drop, Bajón, Outro (elegido por el dueño). Sin modelos nuevos (librosa). |
| Cambiar BPM y tono | **Copia nueva** junto al original (elegido por el dueño), por BPM destino (50–150 % del original) y tonalidad destino (Camelot o ±12 semitonos). Se renderiza con ffmpeg `rubberband` a máxima calidad. |
| Exportar a | **Rekordbox XML, VirtualDJ y Serato** (elegido por el dueño). Traktor queda fuera. |
| Cues | Cada sección es un memory cue con su nombre. Las 8 primeras también son hot cues (A–H), con el color de la sección. |
| Validación | El dueño no tiene Rekordbox ni Serato. Se valida contra los formatos documentados y con tests de ida y vuelta. La prueba real la hace el dueño en su programa. |
| Fuera de alcance | Mejora con IA y vídeo (4b), Traktor, rejillas con cambios de tempo, leer de vuelta las bibliotecas de los programas DJ. |

## 3. Rejilla de beats

**Modelo.** `grid = {anchor: segundos del primer "1", bpm, source: "auto" | "manual", meter: 4}`.

- `beats(grid, duration)` devuelve la lista de golpes que ya usan la onda, el mezclador y el metrónomo.
- Un compás tiene 4 golpes. Los compases se cuentan desde el ancla: también hay compases antes del ancla si la canción empieza antes.

**Análisis.**

- El BPM es el de siempre.
- El ancla es el golpe detectado con más energía en graves entre los 8 primeros, alineado con la rejilla (fase que más golpes detectados explica).
- Los análisis antiguos se convierten al leerlos (ancla = primer golpe de la lista) y se marcan para "Reanalizar".

**Edición en la ficha de datos** (modo "Rejilla" sobre la onda):

- "El 1 aquí" (pone el ancla en el cabezal).
- Mover ±10 ms y ±1 golpe.
- BPM ×2 y ÷2.
- BPM a mano (tap tempo, que ya existe).
- Metrónomo para comprobar la rejilla contra la canción.

Cualquier edición pone `source = "manual"`. Reanalizar mantiene la rejilla manual (igual que el BPM manual), salvo con "Volver al automático".

**API.** `PUT /analysis/grid {path, anchor?, bpm?, shift_ms?, shift_beats?, scale?: 0.5 | 2, reset?: true}` devuelve la rejilla nueva. Si el análisis está caducado responde 409, como el BPM manual.

## 4. Secciones

**Detección** (`djengine/tools/sections.py`, dentro del trabajo de análisis):

1. Características por golpe de la rejilla: energía RMS, MFCC (timbre) y chroma (armonía).
2. Curva de novedad (kernel de Foote sobre la matriz de autosimilitud) por compases.
3. Los cortes candidatos son los picos de novedad. Cada uno se ajusta al límite de 8 compases más cercano de la rejilla. Sección mínima: 8 compases. Máximo: 16 secciones.
4. **Nombres** según la energía media de cada sección, normalizada a la canción:
   - la primera sección se llama Intro si su energía es menor que la mediana;
   - la última se llama Outro en el mismo caso;
   - las secciones de energía alta (> percentil 70) son "Estribillo/Drop";
   - una sección de energía baja después de una alta es "Bajón";
   - una sección que sube de energía antes de una alta es "Subida";
   - el resto, "Verso".

**Datos.** `sections = [{start, end, label, source: "auto" | "manual"}]` en el sidecar. Hay un color por etiqueta: Intro gris, Verso azul, Subida amarillo, Estribillo/Drop rojo, Bajón violeta, Outro gris.

**Edición.** En la onda se ven como bandas de color con su nombre. Se puede:

- renombrar (lista de etiquetas);
- mover un límite (se ajusta a compás; con `Alt`, libre);
- unir con la siguiente;
- partir en el cabezal;
- borrar.

Cualquier edición marca la lista como `manual`, y Reanalizar no la sobrescribe salvo "Volver al automático".

**API.** `PUT /analysis/sections {path, sections}` o `{path, reset: true}`. Valida que las secciones estén ordenadas, no se solapen y queden dentro de la duración.

**Versión.** `ANALYSIS_VERSION` pasa a 2. Los análisis de la versión 1 se muestran con la rejilla convertida y sin secciones, y aparece el aviso "Reanaliza para detectar secciones".

## 5. Cambiar BPM y tono

**Ventana** "Cambiar BPM y tono" (botón en la ficha de datos y en el menú de la biblioteca):

- BPM destino: deslizador y campo, entre 50 y 150 % del original.
- Tonalidad destino: rueda Camelot o ±semitonos (−12…+12), en la notación de Ajustes.
- Formato: el del original por defecto; opciones WAV 16, WAV 24, FLAC, MP3 320.
- Vista previa del nombre del archivo que se va a crear.

**Trabajo `retempo`.**

- `POST /jobs {type: "retempo", path, bpm, semis, format?}`.
- Renderiza con ffmpeg: `rubberband=tempo=<bpm_destino/bpm_original>:pitch=<2^(semis/12)>:pitchq=quality:transients=mixed`.
- Progreso, cancelación e historial como siempre.
- Salida: `«<nombre original> (124 BPM, 9A).<ext>»` en la carpeta del original, con `unique_path` y el límite de MAX_PATH. Se mueve con `_commit` (atómico).
- Etiquetas: se copian las del original; BPM y tonalidad nuevos.
- El archivo nuevo entra en la biblioteca **ya analizado**:
  - BPM = destino;
  - tonalidad desplazada;
  - rejilla: ancla ÷ ratio, BPM destino;
  - secciones: tiempos ÷ ratio;
  - loudness y onda recalculados (análisis ligero, sin BPM ni tonalidad).
- Si el original no está analizado: "Analiza primero" (hace falta el BPM).

## 6. Exportar a programas DJ

**Entrada.** Biblioteca → "Exportar a…" → Rekordbox / VirtualDJ / Serato, para las pistas seleccionadas o toda la biblioteca.

- Trabajo `dj_export {target, track_ids | "all"}` con progreso.
- Resultado: `{exported, skipped: [{title, reason}], file?}`.
- Motivos de pista saltada: "Sin analizar", "Archivo no encontrado", "Formato no compatible con Serato".

**Comunes.**

- Tonalidad en notación musical inglesa (`Am`, `F#`).
- Tiempos en segundos con 3 decimales.
- Cues: memory cue por sección y hot cues A–H para las 8 primeras.
- `djengine/export/` tiene una función pura por destino (datos → texto o bytes) y un escritor separado.

**Rekordbox** (`rekordbox.py`).

- Genera `rekordbox.xml` con:
  - `DJ_PLAYLISTS Version="1.0.0"`;
  - `PRODUCT`;
  - `COLLECTION` con un `TRACK` por pista: `Location` como URL `file://localhost/` codificada, `AverageBpm`, `Tonality`, `TotalTime`, `Kind`, `Size`, `Name`, `Artist`, `Album`;
  - `TEMPO Inizio=<ancla> Bpm Metro="4/4" Battito="1"`;
  - `POSITION_MARK Type="0"`: `Num="-1"` para memory cue y 0–7 para hot cue, con color RGB;
  - `PLAYLISTS` con la carpeta "OneForAll" y las playlists de la app.
- Se guarda donde elija el usuario. Por defecto: `<carpeta de música>/OneForAll rekordbox.xml`.
- Rekordbox lo importa con Preferencias → Avanzado → rekordbox xml.
- **Desfase de MP3:** Rekordbox mide el tiempo desde el principio del audio decodificado; según la cabecera LAME/Xing, el decodificador puede añadir un retardo. Se compensa con el retardo del codificador que declara la cabecera (si existe). El dueño lo comprueba con una pista MP3 en su programa.

**VirtualDJ** (`virtualdj.py`).

- Escribe en la base de datos de VirtualDJ 8: `Documents\VirtualDJ\database.xml` para la unidad del sistema; para pistas en otras unidades, `<unidad>:\VirtualDJ\database.xml`.
- Para cada pista, `Song FilePath`:
  - `Tags` con `Bpm` en segundos por golpe y `Key`;
  - `Scan` con `Bpm` y `Key`;
  - `Poi Type="beatgrid" Pos=<ancla>`;
  - `Poi Type="cue" Num` + `Name` para las secciones.
- Seguridad:
  - Se niega a escribir si VirtualDJ está abierto ("Cierra VirtualDJ para exportar").
  - Copia de seguridad `database.xml.bak-<fecha>`.
  - Fusiona: solo cambia las entradas de nuestras pistas y deja intactas las demás canciones y todos los atributos que no conoce.
  - Escribe de forma atómica.
  - Si el XML existente no se puede leer, aborta sin tocar nada.
  - Si no existe, lo crea.

**Serato** (`serato.py`).

- Escribe dentro de cada archivo las etiquetas que lee Serato, según el formato documentado públicamente ([serato-tags](https://github.com/Holzhaus/serato-tags), MIT):
  - `Serato Autotags`: BPM;
  - `Serato BeatGrid`: un marcador terminal con ancla y BPM;
  - `Serato Markers2`: entradas `CUE` (índice, posición en ms, color, nombre) y `BPMLOCK`.
- Contenedores:
  - MP3: GEOB de ID3v2.4;
  - FLAC: comentarios Vorbis `SERATO_*` en base64, con la cabecera MIME;
  - M4A: átomos `----:com.serato.dj:*`.
- WAV, AIFF y OGG se saltan ("Formato no compatible con Serato").
- Solo toca esas etiquetas; no cambia el audio ni el resto de etiquetas. Después reestampa el análisis y los stems, como con las etiquetas propias (Fase 3a), para que nada quede caducado.

## 7. Errores

| Caso | Comportamiento |
|---|---|
| Pista sin analizar | Cambiar BPM/tono: "Analiza primero". Exportar: se salta y se cuenta. |
| VirtualDJ abierto | `dj_export` falla con "Cierra VirtualDJ para exportar" y no escribe nada. |
| `database.xml` ilegible | Se aborta sin tocarlo: "No se pudo leer la base de datos de VirtualDJ". |
| Archivo bloqueado al escribir etiquetas de Serato | Esa pista se salta ("Archivo en uso"). Las demás continúan. |
| Disco lleno, cancelado o ffmpeg falla | Los códigos de siempre (`disk`, cancelado, `internal`). |
| Rejilla o secciones inválidas en el PUT | 422 con el motivo. |
| BPM destino fuera de 50–150 % | 422 en el motor. La ventana no deja elegirlo. |

## 8. Pruebas

- **Rejilla:**
  - `beats()` desde el ancla y el BPM;
  - conversión desde la lista antigua;
  - cada operación de edición;
  - un análisis con rejilla manual no se sobrescribe al reanalizar;
  - 409 si el análisis está caducado.
- **Secciones:**
  - pistas sintéticas con intro suave, estribillo fuerte de 16 compases, bajón y outro: los cortes caen a ±1 compás y los nombres son los esperados;
  - validación del PUT;
  - las ediciones manuales se respetan.
  - Banco con el dueño: 10 canciones de reguetón de su biblioteca, en las que el dueño marca a oído si cada corte está bien; se apunta el resultado en `docs/bench/`.
- **`retempo`:**
  - seno real: la duración sale × 1/ratio y la frecuencia sube los semitonos pedidos (±1 %);
  - análisis escalado (ancla, secciones, tonalidad);
  - nombre del archivo;
  - cancelar no deja archivos.
- **Rekordbox:**
  - XML generado contra un archivo de referencia (golden), con caracteres especiales y rutas con acentos y espacios;
  - el XML es válido y `Location` se decodifica a la ruta original.
- **VirtualDJ:**
  - fusionar en una base existente conserva las demás canciones y los atributos desconocidos;
  - hay copia de seguridad;
  - el XML ilegible aborta;
  - el bloqueo con VirtualDJ abierto (detección del proceso simulada).
- **Serato:**
  - ida y vuelta: decodificar lo que se escribe devuelve los mismos datos, en MP3, FLAC y M4A;
  - las etiquetas ajenas y el audio no cambian (hash del audio);
  - estructura de bytes contra los ejemplos de la documentación de serato-tags.
- **App (Vitest):**
  - modo Rejilla (cada botón llama al PUT y la onda se redibuja);
  - bandas de secciones y su edición;
  - ventana Cambiar BPM y tono (límites, nombre previsto);
  - menú Exportar a… y su resumen.
- **E2E:** editar la rejilla, cambiar el BPM de una pista (el archivo nuevo aparece analizado en la biblioteca) y exportar a Rekordbox (el archivo existe y contiene la pista).

## 9. Criterios de aceptación

1. La rejilla editada se guarda, sobrevive a reanalizar y se ve igual en la onda, el mezclador y el metrónomo.
2. Las secciones salen en límites de compás y con nombres razonables en el banco del dueño: al menos 7 de cada 10 cortes buenos a oído.
3. El archivo con otro BPM o tono tiene la duración y el tono pedidos, y entra analizado en la biblioteca.
4. Rekordbox, VirtualDJ y Serato reciben BPM, tonalidad, rejilla y cues. Lo comprueba el dueño en el programa que tenga; el resto, con los tests.
5. Exportar nunca estropea datos ajenos: la base de VirtualDJ se conserva, y en Serato no cambian ni el audio ni las demás etiquetas.
6. Pasan todas las suites (motor, Vitest, E2E) y el instalador se genera.

## 10. Riesgos

- **Formatos sin documentación oficial (Serato, VirtualDJ):** se usa solo la parte conocida y estable, con copia de seguridad en VirtualDJ. Si el dueño detecta un fallo al importar, se corrige con su archivo de ejemplo.
- **Desfase en MP3:** Rekordbox, Serato y VirtualDJ compensan de forma distinta el retardo del codificador. Se aplica la compensación documentada y el dueño lo verifica con una pista. Si hay desfase, se ajusta por destino.
- **Secciones en canciones con poca variación:** pueden salir pocas secciones o demasiadas. Por eso hay un mínimo de 8 compases, un máximo de 16 secciones y edición a mano.
