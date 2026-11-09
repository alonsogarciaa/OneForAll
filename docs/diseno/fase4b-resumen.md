# Fase 4b — Mejora con IA y vídeo: resumen de ejecución (2026-11-09)

- Plan: `docs/diseno/plans/2026-11-09-oneforall-fase4b.md`
- Spec: `docs/diseno/specs/2026-11-09-oneforall-fase4b-mejora-video-design.md`
- Rama: `fase4b`

## Qué hay

- **Mejorar audio:** restaura con Apollo (CPU, por trozos de 10 s con fundido). Está en la biblioteca, para una o varias pistas, y en la ficha de datos.
  - Cada vez se elige entre una copia nueva o reemplazar el original, que se guarda en `Originales/`, y entre el mismo formato o FLAC.
  - Se conservan las etiquetas, la portada y las marcas de Serato (en el mismo formato), además del BPM, la rejilla y las secciones.
  - Las pistas mejoradas llevan el distintivo "Mejorado".
- **Escucha A/B de 15 s**, desde el primer estribillo, antes de guardar.
- **Mejorar al descargar:** un ajuste, apagado por defecto. El análisis y los stems se hacen después, sobre el archivo ya mejorado.
- **Exportar vídeo:** un MP4 H.264 + AAC 320 a 720p, 1080p o la calidad máxima.
  - Usa el vídeo original de YouTube, guardado en caché. Las copias con otro BPM aceleran o frenan el vídeo para que vaya sincronizado.
  - Sin vídeo, usa la portada o, si no hay portada, una tarjeta con el título, y lo avisa.
- **Modelo:** el checkpoint oficial (SHA-256 fijado) se convierte una vez a `safetensors` al preparar el instalador. La app nunca carga pickle.

## Verificación

| Prueba | Resultado |
|---|---|
| Motor (pytest) | 441 pasan |
| App (Vitest) | 179 pasan |
| E2E (Playwright, app compilada) | 10 pasan. Incluye mejorar con escucha A/B y exportar vídeo. |
| Diseño a 1280 y 375 px | Capturas en `test-results/enhance-*.png` y `test-results/video-*.png`. Sin desbordes. |
| Instalador | `dist/OneForAll Setup 0.1.0.exe`. Incluye `runtime/models/apollo/apollo.safetensors`. Prueba de humo de la mejora con el Python del instalador: correcta. |
| Puerta de Apollo (`docs/bench/2026-11-fase4b-apollo.md`) | Unos 3,5 s por s de audio en CPU, más que el límite de 3. El dueño decidió seguir solo con CPU. DirectML no se probó. |

## Pendiente del dueño

- La escucha a ciegas de las 5 parejas de `engine/bench/data/apollo/`, apuntada en el banco.
- Probar una mejora completa y una exportación de vídeo en VirtualDJ o Serato Video.

## Revisión final

Se corrigieron estos fallos, cada uno con un test que primero falló:

- Un Opus en el mismo formato fallaba al codificar, porque libopus no acepta 44,1 kHz.
- Reemplazar un archivo de otra unidad fallaba.
- Si la mejora al descargar fallaba, se perdían el análisis y los stems pedidos.
- Un `%` en el título rompía la tarjeta de vídeo.
- Al reanalizar una copia con otro BPM se perdía `origin_bpm`, y su vídeo se desincronizaba.

Quedan 14 detalles menores apuntados en el informe final.
