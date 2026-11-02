# OneForAll — Fase 3a: Stems — Especificación

- Fecha: 2026-11-02
- Estado: pendiente de revisión
- Base: `docs/diseno/specs/2026-11-01-dj-app-design.md` (§8, hoja de ruta) y la Fase 2 (en `main`)
- Referencia: [stemdeck](https://github.com/stemdeckapp/stemdeck) (Apache-2.0): Demucs `htdemucs_6s` y UVR-MDX-NET Karaoke 2.
- La Fase 3 se divide en **3a (stems, esta spec)** y **3b (mezclador de práctica)**.

## 1. Objetivo

Separar cualquier canción de la biblioteca, o cualquier archivo propio, en los stems que el DJ elija. Los stems se guardan en una carpeta configurable, se pueden escuchar, arrastrar a un DAW y exportar en zip. También se pueden pedir directamente desde el buscador ("solo voz", "solo batería"…).

Éxito = los bugs de `review.txt` sobre stems resueltos (no se hacían, abrían otra instancia, creaban la carpeta en el sitio equivocado, la barra seguía animándose tras cancelar, no se podía elegir dónde guardarlos), separación fiable en cualquier PC, y aceleración por GPU solo si la calidad es indistinguible de la CPU.

## 2. Decisiones

| Tema | Decisión |
|---|---|
| Modelo principal | Demucs `htdemucs_6s`: voz, batería, bajo, guitarra, piano y resto (elegido por el dueño). |
| Voz principal / coros | UVR-MDX-NET Karaoke 2 (ONNX) aplicado al stem de voz, con `audio-separator`. Opcional por separación. |
| Cálculo | **CPU por defecto** (Ryzen 5 5600X: unos 14 s por cada 30 s de audio, alrededor de 2 min por canción). |
| Prueba con la GPU AMD (2026-11-02) | `torch-directml` con STFT, máscara e iSTFT en la CPU corre 2,2 veces más rápido en la RX 9060 XT, pero se desvía de la CPU (relación señal/error: bajo 6,4 dB, guitarra 2,1 dB, resto 4,5 dB). **Descartado.** |
| Aceleración AMD/Intel | Intento con el núcleo de Demucs exportado a ONNX y ejecutado con `onnxruntime-directml`. Solo se activa si supera el umbral de §6. NVIDIA/CUDA queda fuera (el dueño usa AMD y añadiría unos 2,5 GB al instalador). |
| Formato de los stems | WAV 16 bits a 44,1 kHz por defecto. Ajuste: WAV 24 bits, FLAC, MP3 320. |
| Carpeta | Ajuste `stems_dir`, por defecto `<carpeta de música>/Stems`. Cada canción en `<stems_dir>/<Artista - Título>/`. |
| Nombres de archivo | `voz`, `bateria`, `bajo`, `guitarra`, `piano`, `resto`, `voz_principal`, `coros` + extensión. |
| Fuera de alcance | El mezclador (velocidad, tono, bucles, metrónomo, exportar mezcla o bucle): Fase 3b. |

## 3. Motor

### 3.1 Módulos (`engine/djengine/stems/`)

| Módulo | Interfaz | Notas |
|---|---|---|
| `models.py` | `ensure_model(name) -> Path` | Copia los modelos incluidos (`ONEFORALL_MODELS`) a la caché de cada librería; si no están incluidos, los descarga (con checksum). |
| `separate.py` | `separate(path, wanted: set[str], out_dir, report, cancelled) -> dict[str, Path]` | Demucs `apply_model(split=True, overlap=0.25, shifts=0)` por trozos, para informar del progreso y comprobar la cancelación entre trozos. Escribe solo los stems pedidos. |
| `karaoke.py` | `split_vocals(vocals_path, out_dir) -> (lead, backing)` | audio-separator con `UVR_MDXNET_KARA_2.onnx`. Proveedor DirectML si está disponible; si no, CPU. |
| `accel.py` | `backend() -> "directml" \| "cpu"`, `demucs_onnx_available() -> bool` | Ajuste `stems_backend`: `auto` (por defecto), `cpu`. `auto` usa DirectML solo si el modelo ONNX validado está presente y DirectML carga. |
| `runner.py` | `make_stems_runner(svc, path, wanted, karaoke) -> Runner` | Etapas `loading_model`, `separating` (porcentaje por trozos), `karaoke`, `encoding`, `saving`. Usa `begin_finalize` antes de mover los archivos a su carpeta final. |
| `store.py` | tabla `stems(path TEXT, stem TEXT, file TEXT, model TEXT, size INTEGER, mtime REAL, created_at TEXT, PRIMARY KEY(path, stem))` | Caché: un stem ya separado de la misma versión del archivo (tamaño + mtime) no se vuelve a calcular. |

### 3.2 Trabajos y API

- Tipo de trabajo `stems`, concurrencia **1** (satura la CPU). Cancelable. Cancelar no deja archivos parciales: todo se escribe en `tmp/<job>` y se mueve al final.
- `POST /jobs {"type":"stems","paths":[...],"stems":["vocals","drums",...],"karaoke":false}`. Los valores válidos de `stems` son `vocals, drums, bass, guitar, piano, other`. `karaoke: true` implica `vocals`.
- `POST /jobs {"type":"download", ..., "then_stems": {"stems":[...],"karaoke":false}}`: al terminar la descarga, encola un trabajo `stems` independiente (como el análisis automático).
- `GET /stems?path=` → `{"stems": [{"stem","file","size_bytes"}], "folder"}`.
- `POST /stems/zip {"path"}` → crea `<carpeta>/<Artista - Título> (stems).zip` y devuelve su ruta.
- `/audio` acepta también los archivos de stems registrados en la tabla `stems`.
- Errores: modelo no disponible sin conexión → `UserError("model_missing", "Falta el modelo de separación y no hay conexión para descargarlo")`. Audio ilegible → `unreadable` (Fase 2).

### 3.3 Electron

- IPC `drag:start(path)` → `webContents.startDrag({file, icon})` para arrastrar un stem a un DAW o al Explorador. Solo acepta archivos de la tabla `stems` (el renderer pide primero la lista al motor; main valida extensión y existencia).

## 4. Interfaz

- **Panel "Separar stems"** (GlassSheet):
  - 6 casillas: Voz, Batería, Bajo, Guitarra, Piano, Resto. Por defecto, las 4 primeras.
  - Interruptor "Separar voz principal y coros".
  - Estimación "≈ 2 min en este equipo", calculada con el tiempo medio de los trabajos anteriores o, si no hay, con 4 s por cada 10 s de audio.
  - Botón "Separar".
  - Se abre desde: la biblioteca (botón de la barra para la selección y opción en la fila), la ventana de datos y el historial.
- **Buscador:** el menú de descarga (FormatMenu) añade un bloque "Stems" con las opciones "Solo voz", "Solo batería", "Solo bajo", "Todos los stems" y "Elegir…". Cada una descarga la canción y luego separa.
- **Ventana de datos:** sección "Stems" con una fila por stem: icono, nombre, reproducir/pausa (un solo reproductor compartido), tamaño, **asa de arrastre**. Debajo, "Mostrar carpeta" y "Exportar zip". Mientras se separa, progreso por etapa y Cancelar.
- **Biblioteca:** columna "Stems" con un icono si la canción tiene stems guardados.
- **Descargas:** los trabajos `stems` aparecen como el resto, con las etapas "Cargando modelo", "Separando 45 %", "Separando voces", "Codificando" y "Guardando". Al cancelar, la barra se detiene y vuelve a 0.
- **Ajustes, sección "Stems":**
  - Carpeta de stems (Cambiar…).
  - Formato (WAV 16 / WAV 24 / FLAC / MP3 320).
  - Cálculo: Automático / Solo CPU, con el backend activo indicado ("Usando: CPU" o "Usando: GPU (DirectML)").

## 5. Pruebas

- **Rápidas (modelo falso inyectado):**
  - El runner escribe solo los stems pedidos, con los nombres de §2 en `<stems_dir>/<Artista - Título>/`.
  - La caché evita recalcular; si el archivo cambia, se recalcula.
  - Cancelar en mitad de la separación no deja nada en la carpeta final ni en `tmp/`.
  - `karaoke: true` añade `voz_principal` y `coros`.
  - Los formatos WAV 16/24, FLAC y MP3 se leen con mutagen.
  - El zip contiene exactamente los stems guardados.
  - `/audio` sirve los stems registrados y da 403 a lo demás.
  - "Descargar → solo voz" encola `stems` con `["vocals"]` cuando termina la descarga.
  - `drag:start` rechaza rutas que no son stems.
- **Lenta (`-m slow`):** `htdemucs_6s` real sobre 10 s de audio sintético (clics + bajo + tono). La batería concentra la energía de los clics y el bajo la del tono grave.
- **UI (Vitest):** panel de stems (casillas por defecto, estimación), bloque Stems del menú de descarga, sección Stems de la ventana de datos, ajustes.
- **E2E (motor fake con separador falso):** separar desde la biblioteca → la ventana de datos lista los stems → "Exportar zip" crea el archivo.

## 6. Aceleración ONNX + DirectML (tarea con puerta)

1. Exportar el núcleo de `htdemucs_6s` a ONNX con la STFT y la iSTFT fuera del grafo (calculadas en numpy/torch en la CPU, como en la prueba). Ejecutar con `onnxruntime-directml`.
2. **Validación:** en 5 canciones reales de la biblioteca de prueba, la relación señal/error de cada stem respecto a la CPU de PyTorch debe ser **≥ 40 dB**, y el tiempo debe mejorar al menos 1,5 veces.
3. Si se cumple, `auto` usa DirectML en AMD/Intel. Si no, se queda en CPU y los números se documentan en `docs/bench/2026-11-fase3a-accel.md`. En ambos casos la fase sigue adelante.

## 7. Criterios de aceptación

1. "Separar stems" con Voz + Batería + Bajo sobre una canción real crea exactamente esos 3 archivos en `<stems_dir>/<Artista - Título>/`, en unos 2 min en el equipo del dueño (CPU).
2. "Separar voz principal y coros" añade `voz_principal` y `coros`.
3. "Descargar → Solo voz" desde el buscador deja la canción en la biblioteca y `voz.wav` en su carpeta de stems.
4. Cancelar una separación detiene la barra, no deja archivos y no afecta a otros trabajos. No se abre ninguna otra instancia de la app.
5. La ventana de datos reproduce cada stem; arrastrarlo al Explorador copia el archivo; "Exportar zip" crea el zip.
6. Cambiar la carpeta y el formato en Ajustes se aplica a las separaciones siguientes.
7. El informe de aceleración existe, y DirectML solo está activo si cumplió §6.

## 8. Riesgos

- **Tiempo en CPU:** unos 2 min por canción. Se mitiga con la cola en segundo plano, una estimación visible y la caché.
- **Exportar htdemucs a ONNX** (transformer con atención cruzada) puede no ser posible o no alcanzar 40 dB → se queda en CPU (§6).
- **Tamaño del instalador:** unos 130 MB más con los modelos `htdemucs_6s` y Karaoke 2.
- **Licencias:** Demucs (MIT), pesos `htdemucs_6s` (MIT), audio-separator (MIT), modelo UVR Karaoke 2 (licencia del autor; uso personal). Se anota en el README.
