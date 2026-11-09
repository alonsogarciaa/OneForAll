# Banco Fase 5a: Descubrir (2026-11-10)

Script: `python -m bench.discover_bench`, ejecutado contra los servicios reales. Equipo: Ryzen 5 5600X.

## Emparejado de Spotify

Objetivo de la spec: de 50 canciones, al menos 45 `found` sin revisar.

| Playlist | Canciones | found | review | missing | % found |
|---|---|---|---|---|---|
| Today's Top Hits | 50 | 49 | 1 | 0 | 98 % |
| Top 50: España | 50 | 50 | 0 | 0 | 100 % |
| Viva Latino | 50 | 50 | 0 | 0 | 100 % |

**Cumple.**

Revisé a mano 30 de los `found` (10 por lista) y todos eran la canción correcta.
- Los remixes se emparejan con su remix: "PARADIXE - REMIX" con "PARADIXE (REMIX)" y "Body - Remix" con "Body (Remix)".
- Las colaboraciones también: "expectations (feat. Chappell Roan)" con "expectations".

## Recomendaciones con BPM y tonalidad

Objetivo de la spec: al menos 20 recomendaciones, y el 80 % con BPM y tonalidad en menos de un minuto.

| Semilla | Recomendaciones | Con datos | Tiempo para el 80 % | Ajuste |
|---|---|---|---|---|
| LA GRACIOSA (Kev3r6W4TPo) | 49 | 49 | 113 s | 50 filas, 2 a la vez |
| CONTIGO (n5ZZnwDhuow) | 49 | 49 | 71 s | 50 filas, 4 a la vez |
| BUENAS NOCHES (TNb6aBmx3O8) | 25 | 25 | 39 s | **25 filas, 4 a la vez (final)** |
| LA GRACIOSA (Kev3r6W4TPo) | 25 | 25 | 32 s | **25 filas, 4 a la vez (final)** |

- Un fragmento tarda unos 10 s: 4 s de descarga y 5 s de análisis.
- Con la configuración final (25 recomendaciones y 4 análisis a la vez) **se cumple**: 100 % con datos y el 80 % en 32–39 s.
- Ejemplo de precisión: "ABC" (Hoke, Quevedo) da 138 BPM y 4A con el fragmento de 60 s.
