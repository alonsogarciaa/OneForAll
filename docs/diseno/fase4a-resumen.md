# Fase 4a — Herramientas DJ: resumen de ejecución (2026-11-06)

Plan: `docs/diseno/plans/2026-11-06-oneforall-fase4a.md`. Spec: `docs/diseno/specs/2026-11-06-oneforall-fase4a-herramientas-dj-design.md`. Rama `fase4`.

## Qué hay

- **Rejilla fija** (el "1" + BPM) en la ficha de datos, modo "Rejilla": el 1 aquí, ±10 ms, ±1 golpe, ÷2 y ×2, volver al automático y metrónomo. Una rejilla manual sobrevive a reanalizar.
- **Secciones** detectadas en el análisis (versión 2): cortes en frases de 8 compases y nombres por energía (Intro, Verso, Subida, Estribillo/Drop, Bajón, Outro). Se ven como bandas sobre la onda. El editor permite renombrar, mover el inicio al cabezal, unir, partir, borrar y volver al automático.
- **Cambiar BPM y tono:** crea una copia nueva entre el 50 y el 150 % del BPM y a ±12 semitonos, renderizada con rubberband. La copia queda en la biblioteca ya analizada, con la rejilla y las secciones escaladas.
- **Exportar a Rekordbox (XML), VirtualDJ (database.xml) y Serato (etiquetas):** BPM, tonalidad, rejilla y cues. Al terminar muestra un resumen con las pistas saltadas y el motivo.

## Verificación

| Prueba | Resultado |
|---|---|
| Motor (pytest) | 368 pasan |
| App (Vitest) | 166 pasan |
| E2E (Playwright, app compilada) | 9 pasan. Incluye editar la rejilla, la copia con otro BPM analizada en la biblioteca y la exportación a Rekordbox. |
| Diseño a 1280 y 375 px | Capturas en `test-results/`. Sin desbordes laterales (corregidos la barra de acciones y la fila de tap tempo). |
| Banco de secciones (`docs/bench/2026-11-fase4a-secciones.md`) | 6 pistas reales. Falta que el dueño marque los cortes a oído. |

## Pendiente del dueño

- Marcar los cortes del banco a oído (meta: 7 de cada 10).
- Importar en su programa DJ (Rekordbox, VirtualDJ o Serato) y comprobar BPM, rejilla y cues, sobre todo el posible desfase en MP3.
