# Fase 3b — Mezclador de práctica: resumen de ejecución (2026-11-05)

Plan: `docs/diseno/plans/2026-11-05-oneforall-fase3b.md`. Spec: `docs/diseno/specs/2026-11-05-oneforall-fase3b-mezclador-design.md`. Rama `fase3b`.

## Qué hay

- **Mezclador** (botón "Mezclador" en la sección Stems de la ficha de datos, con 2 stems o más):
  - silencio, solo, volumen y semitonos por stem;
  - velocidad 0,50–1,00× sin cambiar el tono; tonalidad global ±12 (Camelot resultante);
  - bucle arrastrando sobre la onda, ajustado a los golpes (`Alt`: sin ajuste);
  - metrónomo con cuenta atrás, compás 2/4 a 6/8 y desplazamiento del 1;
  - atajos `Espacio` y `L`.
- **Exportar:** mezcla completa o solo el bucle, en WAV 16 o 24 bits, FLAC o MP3, renderizado con ffmpeg `rubberband`. El archivo resultante se puede arrastrar al DAW. El zip de stems también está en ese menú.
- **Ajustes por canción:** se guardan en el motor y se restauran al reabrir.

## Verificación

| Prueba | Resultado |
|---|---|
| Motor (pytest) | 300 pasan |
| App (Vitest) | 114 pasan |
| E2E (Playwright, app compilada con la CSP de producción) | 8 pasan. Incluye la reproducción real con el worklet, el bucle, la exportación del bucle y el estado restaurado. |
| Sincronía entre stems (spike, `docs/bench/2026-11-fase3b-stretch.md`) | 6 nodos idénticos muestra a muestra |
| CPU en vivo, 6 stems a 0,5× | 17 % de un núcleo |
| Exportación real (BUENAS NOCHES, bucle de 20 s, 0,5× y +3) | 40,0 s exactos, pico 0,99 (limitador), 21 s de render |
| Diseño a 1280 px y 375 px | Capturas en `test-results/`. A 375 px todo se apila, sin desplazamiento horizontal. |

## Pendiente de escucha (dueño)

La calidad audible a 0,5× y +3 en vivo y exportada, y la ausencia de clics al mover los controles, solo se pueden juzgar escuchando. Hay que probarlo con la app instalada (`dist/OneForAll Setup 0.1.0.exe`).
