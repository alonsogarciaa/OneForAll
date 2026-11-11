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

- **Revisión final:** las cifras anteriores se midieron sin querer con los estimadores de respaldo, porque `quick.py` no registraba DeepRhythm ni CNN. Ya está corregido. Medido otra vez con los estimadores reales de la app:

| Semilla | Recomendaciones | Con datos | 80 % | Configuración |
|---|---|---|---|---|
| BUENAS NOCHES | 25 | 25 | 75 s | 60 s de fragmento, 4 a la vez |
| LA GRACIOSA | 25 | 25 | 66 s | 60 s de fragmento, 4 a la vez |
| BUENAS NOCHES (en frío) | 25 | 25 | 64 s | **tonalidad sobre los 30 s centrales, 4 a la vez (final)** |
| LA GRACIOSA (modelos cargados) | 25 | 25 | 55 s | ídem |
| CONTIGO (en frío) | 25 | 25 | 70 s | ídem, 6 a la vez (sin mejora) |
| BUENAS NOCHES (modelos cargados) | 25 | 25 | 56 s | ídem, 6 a la vez |

- **Coste por canción, con los modelos ya cargados:** descarga 4 s, decodificación 0,5 s, tempo con DeepRhythm 0,3 s y tonalidad con CNN 2,3 s sobre 60 s (1,2 s sobre 30 s). La CNN se ejecuta de una en una.
- **Resultado:** con los modelos ya cargados, **cumple** (55–56 s). La primera vez de cada sesión, que incluye cargar los modelos, va algo por encima (64–70 s). Se queda así y se avisa al dueño.
