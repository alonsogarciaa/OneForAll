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
| Motor (pytest) | 539 pasan |
| App (Vitest) | 219 pasan |
| E2E (Playwright) | 12 pasan, incluidas Descubrir con "Parecidas" e importar desde Spotify. |
| Diseño | Las pantallas, a 1280 px y a 1024 px (el ancho mínimo de la ventana); las hojas, a 375 px. Sin desbordes. |
| Banco (`docs/bench/2026-11-fase5a-descubrir.md`) | Emparejado: 98–100 % `found`. Recomendaciones: 25 con datos, el 80 % en 55–56 s con los modelos cargados y en 64–70 s la primera vez de cada sesión. |

## Pendiente del dueño

- Probar con tus propias playlists de Spotify o Apple Music, y con alguna de SoundCloud.

## Revisión final

Se corrigieron 8 fallos importantes, cada uno con un test que primero falló:
- El análisis rápido usaba los estimadores de respaldo.
- Un enlace de canción de Apple Music importaba el álbum entero.
- Las canciones que ya tenías no entraban en la playlist importada.
- Las versiones "(Official Live Video)" empataban con la original.
- En los sets de SoundCloud, las entradas venían incompletas y las Go+ no se marcaban.
- El aviso de Descubrir seguía visible después de elegir una canción.
- Las playlists de moods largas se quedaban colgadas.
- Al cerrar Importar no se cancelaba el emparejado.

Quedan detalles menores apuntados en el informe final.
