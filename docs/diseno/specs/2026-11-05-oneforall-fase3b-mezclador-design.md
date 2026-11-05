# OneForAll — Fase 3b: Mezclador de práctica — Especificación

- Fecha: 2026-11-05
- Estado: aprobada (2026-11-05)
- Base: `docs/diseno/specs/2026-11-01-dj-app-design.md` (§8, hoja de ruta) y la Fase 3a (stems, en `main`)
- Referencia: [stemdeck](https://github.com/stemdeckapp/stemdeck) (Apache-2.0), mezclador de práctica sobre stems.

## 1. Objetivo

Practicar y preparar sobre los stems de una canción. Cada stem se puede silenciar, poner en solo o cambiar de volumen. La canción se puede ralentizar sin cambiar el tono, repetir un fragmento en bucle, cambiar de tonalidad (la canción entera o un solo stem) y tocar con un metrónomo alineado con la canción. El resultado se exporta (mezcla entera o solo el bucle) y se arrastra a un DAW.

Éxito: los cambios de velocidad y tonalidad se oyen al momento, sin cortes. Los stems nunca se desincronizan. El archivo exportado suena como lo que se estaba escuchando, pero renderizado a calidad máxima.

## 2. Decisiones

| Tema | Decisión |
|---|---|
| Reproducción | **En tiempo real en la app** (elegido por el dueño): Web Audio con un AudioContext y un reloj para todos los stems. |
| Velocidad y tono en vivo | [Signalsmith Stretch](https://github.com/Signalsmith-Audio/signalsmith-stretch) (MIT, WebAssembly en un AudioWorklet), un nodo por stem. Tempo y tono son independientes, así que el tono se puede cambiar por stem. |
| Exportación | El motor renderiza con ffmpeg y el filtro `rubberband` (ya está en el ffmpeg incluido), con la máxima calidad (`pitchq=quality`). |
| Descartados | SoundTouch (artefactos metálicos a 0,5×). Reproducción en el motor Python (unos 200 ms de latencia y difícil de sincronizar con la interfaz). |
| Velocidad | 0,50–1,00×, en pasos de 0,01. Atajos: 0,5 / 0,75 / 0,9 / 1,0. |
| Tonalidad | −12 a +12 semitonos global, más −12 a +12 por stem, que se suman. El total se limita a ±12. |
| Duración máxima | **12 minutos** en el mezclador. Seis stems estéreo en float32 ocupan unos 85 MB por stem cada 4 min; con 12 min y 8 stems, unos 2 GB. Para más, el mensaje es "Pista demasiado larga para el mezclador". |
| Voz principal y coros | Si existen, sustituyen a `vocals` en el mezclador, para que la voz no suene duplicada. |
| Ajustes por canción | Se guardan en el motor (tabla `mixer_state`) y se restauran al reabrir. |
| Fuera de alcance | Efectos (EQ, reverb), grabar encima, MIDI, exportar el metrónomo, varias canciones a la vez. |

## 3. Interfaz

**Entrada.** Botón "Mezclador" en `StemsSection`, en la ficha de datos y en la hoja de stems, cuando la canción tiene al menos 2 stems. Abre `MixerSheet` a pantalla completa (un `GlassSheet` grande, según `Liquid_Glass.md`).

**Carga.** Muestra "Cargando stems… n/N". Cada stem se descarga por `/audio` y se decodifica con `decodeAudioData`. Los canales pasan al nodo de Signalsmith y el `AudioBuffer` se suelta enseguida, para no tener el audio dos veces en memoria.

**Zonas, de arriba abajo:**

1. **Onda.** La de 3 bandas de la Fase 2 (sidecar de análisis), con cabezal.
   - Clic: saltar a ese punto.
   - Arrastrar: marcar el bucle A–B, que se ajusta al golpe más cercano de la rejilla. Con `Alt` pulsado no se ajusta.
   - Las asas del bucle se pueden arrastrar. `L` activa o quita el bucle.
   - Sin análisis, la onda se calcula en la app a partir de la suma de los stems y no hay ajuste a golpes.
2. **Transporte.**
   - Play/pausa (`Espacio`, con las mismas exclusiones que la ficha de datos: campos de texto, `select`, `contenteditable`, tecla mantenida).
   - Volver al inicio, o al inicio del bucle si está activo.
   - Tiempo actual / total, en tiempo de la canción original.
3. **Controles globales.**
   - Velocidad: deslizador más atajos. Muestra "BPM 128,0 → 96,0".
   - Tonalidad: −/+ con la tonalidad resultante en la notación elegida en Ajustes, por ejemplo "8A → 10A".
   - Volumen general.
4. **Tiras de stems,** una por stem, en el orden de `names.STEMS`:
   - nombre y color;
   - M (silenciar) y S (solo, varios a la vez);
   - volumen de 0 a 150 %, con doble clic para volver a 100 %;
   - semitonos propios, −/+.
5. **Metrónomo.**
   - Activar o desactivar, y volumen.
   - Cuenta atrás de 0, 1 o 2 compases.
   - Compás 2/4, 3/4, 4/4 o 6/8, con acento en el 1.
   - "1 ←/→": desplaza el primer tiempo un golpe.
6. **Exportar** (menú):
   - "Mezcla completa" y "Solo el bucle" (desactivado si no hay bucle), en WAV, FLAC o MP3; por defecto, `stems_format` de Ajustes.
   - "Stems (zip)", que ya existe.
   - Al terminar, el resultado aparece en la hoja con "Mostrar en carpeta" y se puede arrastrar al DAW.

**Solo y silencio.** Si algún stem tiene solo, suenan solo los que tienen solo. Si no, suenan todos menos los silenciados. Los cambios de ganancia usan rampas de 10 ms para evitar clics.

**Al cerrar.** El audio se para, los nodos se desconectan y se cierra el AudioContext. La memoria queda libre.

## 4. Audio en la app

Hay módulos sin interfaz en `ui/src/mixer/`, que la hoja solo usa. Así se prueban con un AudioContext falso.

- **`engine.ts` (`MixerEngine`)**
  - API: `load(stems)`, `play()`, `pause()`, `seek(t)`, `setLoop(a, b | null)`, `setRate(r)`, `setGlobalSemis(n)`, `setStem(name, {gain, mute, solo, semis})`, `setMaster(g)`, `position()` en tiempo de la canción original, `dispose()`.
  - Cada stem: nodo Signalsmith → `GainNode` → master → destino.
  - Sincronía: todas las órdenes (arranque, salto, cambio de velocidad, bucle) se programan para la **misma hora del reloj del audio**, `ctx.currentTime + 0,05 s`, en todos los nodos a la vez.
  - El bucle lo ejecuta el propio nodo (`loopStart` / `loopEnd`), con precisión de muestra.
- **`metronome.ts`**
  - Programador con anticipación: cada 25 ms programa los clics de los próximos 100 ms. Son osciladores cortos, con un tono más agudo en el 1.
  - Los golpes salen de la rejilla del análisis, convertida a tiempo de reproducción (`t_reproducción = t_canción / velocidad`, desde el último arranque). Sin rejilla usa el BPM. Sin BPM, el metrónomo queda desactivado con el aviso "Sin BPM".
  - Cuenta atrás: n compases de clics antes de que arranque el audio.
  - En bucle, los clics siguen la vuelta del bucle.
- **`mixState.ts`**: el estado serializable (volúmenes, silencios, solos, semitonos, velocidad, bucle, ajustes del metrónomo) y su validación al cargarlo.
- **Seguridad (CSP).** El WebAssembly necesita `'wasm-unsafe-eval'` en `script-src`, y nada más. El worklet y el `.wasm` van en el propio paquete, nunca desde una CDN.

## 5. Motor

- **`GET /mixer/state?path=` y `PUT /mixer/state {path, state}`**
  - Tabla `mixer_state(path_key PRIMARY KEY, state_json, updated_at)` en la base de datos de la app. Usa la misma clave normalizada que `StemsStore`.
  - `state` se valida con un modelo pydantic: rangos de §2 y solo stems conocidos.
  - La app guarda 500 ms después del último cambio.
- **Trabajo `mix_export`**: `POST /jobs {type:"mix_export", path, state, range: "full" | "loop", format}`.
  - Comprueba que existen los stems y aplica el límite de 12 min.
  - Construye el grafo de filtros con una función pura, `build_mix_graph(stems, state, range)`:
    - por cada stem que suena: `atrim` (si es solo el bucle) → `rubberband=tempo=r:pitch=2^(semis/12):pitchq=quality:transients=mixed` → `volume`;
    - después, `amix=inputs=n:normalize=0`, y `volume` del master;
    - por último, `alimiter=limit=0.99:level=false`, solo como protección.
  - Progreso a partir de `out_time` de ffmpeg; cancelar mata ffmpeg, como en la conversión.
  - Salida: en la carpeta de stems de la canción, `mix (0.75x, +2).<ext>` o `loop 01m12s-01m28s (0.75x).<ext>`. Si el nombre existe, se usa `unique_path`, y se aplica el límite de MAX_PATH.
  - Se mueve con `_commit` (atómico) y se apunta en el historial ("export").
  - El archivo exportado se añade a la lista de arrastre del motor (`/stems/check` lo confirma).
- Ningún paquete Python nuevo.

## 6. Errores

| Caso | Comportamiento |
|---|---|
| Un stem borrado o ilegible | El mezclador no abre. Mensaje "Faltan stems de esta canción", con botón "Separar de nuevo". |
| Decodificación sin memoria | "No hay memoria suficiente para el mezclador". Se libera todo. |
| AudioContext suspendido por el sistema | Se reanuda con el siguiente play. |
| La pista cambió desde la separación | Los stems ya se invalidan (Fase 3a). El mezclador ofrece volver a separar. |
| Estado guardado inválido o de otra versión | Se descarta y se usa el estado por defecto. |
| Exportación: disco lleno, cancelada o ffmpeg falla | Los códigos de siempre (`disk`, cancelado, `internal`) en la lista de trabajos y en el historial. |
| Exportar "Solo el bucle" sin bucle | El botón está desactivado. El motor responde 422. |

## 7. Pruebas

- **Motor (pytest)**
  - `build_mix_graph`: solo, silencio, semitonos sumados y limitados, recorte del bucle, ningún stem audible (422).
  - `mix_export` con stems sintéticos de 3 s y ffmpeg real: la duración sale ≈ 3 / velocidad, y la frecuencia de un seno sube los semitonos pedidos (FFT, ±1 %).
  - Cancelar no deja archivos.
  - `/mixer/state`: guardar, leer, rangos inválidos dan 422, rutas en mayúsculas o minúsculas dan el mismo estado.
- **App (Vitest)**
  - `MixerEngine` con un AudioContext falso: lógica de solo y silencio, mismas horas de arranque en todos los nodos, `setLoop` y `seek` dentro del bucle.
  - `metronome`: horas de los clics con la rejilla y la velocidad, acento en el 1, cuenta atrás, vuelta del bucle.
  - `mixState`: validación y valores por defecto.
  - `MixerSheet`: carga, controles, guardado diferido, menú de exportar.
- **E2E (Playwright, motor falso):** separar, abrir el mezclador, cambiar la velocidad, marcar un bucle, exportar el bucle, el trabajo termina, cerrar y reabrir restaura el estado.
- **Escucha a mano** con la app instalada: DESPECHÁ a 0,5× y a +3 semitonos en vivo y exportado. Sin desincronización tras 5 min en bucle, y sin cortes al mover los deslizadores.

## 8. Criterios de aceptación

1. Mover la velocidad o la tonalidad se oye en menos de 100 ms, sin clics ni cortes.
2. Tras 10 minutos de reproducción con cambios, los stems siguen alineados: diferencia ≤ 1 bloque de audio (128 muestras), medida en la prueba de la app.
3. El bucle vuelve sin hueco audible y el metrónomo cae en los golpes del análisis.
4. La exportación coincide con lo escuchado (mismos stems, volúmenes, velocidad y tono), con calidad `rubberband` y sin saturación.
5. El estado de cada canción se restaura al reabrir.
6. Pasan todas las suites (motor, Vitest, E2E) y el instalador se genera e instala.

## 9. Riesgos

- **Calidad de Signalsmith a 0,5×.** Si la escucha a mano no convence, el plan de reserva es Rubber Band WASM (GPL; compatible porque la app ya incluye código AGPL), con la misma interfaz de `MixerEngine`. La primera tarea del plan es una prueba corta con la API real del paquete: sincronía de 6 nodos, bucle y consumo de CPU.
- **CPU:** seis u ocho nodos de estiramiento en tiempo real. Si se pasan del presupuesto en el Ryzen 5 5600X, se baja la calidad en vivo del nodo; la exportación no cambia.
- **Memoria:** mitigada con el límite de 12 minutos y soltando los `AudioBuffer` tras pasarlos al nodo.
- **CSP:** `'wasm-unsafe-eval'` amplía `script-src` solo para WebAssembly. No permite `eval` de JavaScript.
