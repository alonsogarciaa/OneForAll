# Fase 5a — Descubrir: resumen de ejecución (2026-11-10)

- Plan: `docs/diseno/plans/2026-11-10-oneforall-fase5a.md`
- Spec: `docs/diseno/specs/2026-11-10-oneforall-fase5a-descubrir-design.md`
- Rama: `fase5a`

## Qué hay

- **Descubrir**, pantalla nueva:
  - **Parecidas a…:** la radio de YouTube Music de una canción de tu biblioteca. Se abre también con "Parecidas" desde la biblioteca y desde la ficha de datos.
  - **Moods y géneros:** los de YouTube Music, con una referencia de BPM y tonalidad que pones tú.
  - Cada fila muestra su BPM y su tonalidad, calculados con un fragmento de 60 s y guardados en caché para siempre, con el distintivo **Encaja** o **Cerca**.
  - Se pueden ordenar por "Mejor encaje".
- **SoundCloud** en el buscador: búsqueda y descarga. Las pistas Go+ salen como "Solo vista previa".
- **Importar enlaces** de Spotify, Apple Music y SoundCloud, pegándolos en el buscador. Cada canción se empareja con YouTube Music (✓, Revisar o No encontrada) y "Descargar todas" crea una playlist en la biblioteca.

## Verificación

| Prueba | Resultado |
|---|---|
| Motor (pytest) | Ver el informe final |
| App (Vitest) | Ver el informe final |
| E2E (Playwright) | 12 pasan, incluidas Descubrir con "Parecidas" e importar desde Spotify. |
| Diseño | Las pantallas, a 1280 px y a 1024 px (el ancho mínimo de la ventana); las hojas, a 375 px. Sin desbordes. |
| Banco (`docs/bench/2026-11-fase5a-descubrir.md`) | Emparejado: 98–100 % `found`. Recomendaciones: 25 con datos, el 80 % en 32–39 s. |

## Pendiente del dueño

- Probar con tus propias playlists de Spotify o Apple Music, y con alguna de SoundCloud.
