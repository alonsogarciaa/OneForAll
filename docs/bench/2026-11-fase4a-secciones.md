# Fase 4a — Banco de secciones (2026-11-06)

Análisis real (motor de la app: DeepRhythm, CNN de tonalidad, rejilla fija y secciones) sobre las pistas de `~/Music/OneForAll`. Solo hay 6 pistas en la biblioteca, no 10: el banco se amplía cuando haya más.

| Pista | BPM | 1 en (s) | Secciones | Cortes detectados | Tiempo |
|---|---|---|---|---|---|
| Hoke, Quevedo - ABC | 137.0 | 1.127 | 6 | 0:00 Intro · 0:15 Verso · 1:11 Estribillo/Drop · 1:25 Bajón · 1:39 Estribillo/Drop · 2:21 Verso | 13 s |
| Lucho RK - AIRE | 96.0 | 0.741 | 4 | 0:00 Intro · 0:40 Estribillo/Drop · 1:40 Bajón · 2:00 Verso | 6 s |
| Lucho RK - CONTIGO | 92.0 | 2.108 | 5 | 0:00 Intro · 0:22 Estribillo/Drop · 1:46 Verso · 2:07 Estribillo/Drop · 2:28 Outro | 7 s |
| Lucho RK, La Pantera - BANE | 125.0 | 0.200 | 6 | 0:00 Intro · 0:15 Verso · 0:30 Subida · 1:17 Estribillo/Drop · 2:03 Verso · 2:49 Outro | 7 s |
| Quevedo - BUENAS NOCHES | 103.0 | 1.909 | 6 | 0:00 Intro · 0:39 Estribillo/Drop · 0:57 Bajón · 1:53 Verso · 2:31 Estribillo/Drop · 3:26 Outro | 9 s |
| Quevedo, Elvis Crespo - LA GRACIOSA | 109.0 | 0.689 | 6 | 0:00 Intro · 0:18 Subida · 1:46 Estribillo/Drop · 2:39 Bajón · 3:14 Estribillo/Drop · 3:49 Outro | 10 s |


## Para el dueño: marca cada corte a oído

En cada pista, abre la ficha de datos y escucha cada corte. Apunta cuántos están bien, es decir, la canción cambia ahí y el nombre encaja.

| Pista | Cortes buenos / total | Notas |
|---|---|---|
| Hoke, Quevedo - ABC | / | |
| Lucho RK - AIRE | / | |
| Lucho RK - CONTIGO | / | |
| Lucho RK, La Pantera - BANE | / | |
| Quevedo - BUENAS NOCHES | / | |
| Quevedo, Elvis Crespo - LA GRACIOSA | / | |

Criterio de la spec (§9): al menos 7 de cada 10 cortes buenos.

## Cambios que trajo el banco y la revisión

- Ahora solo se corta donde la canción cambia de verdad: por encima del cambio medio de la canción y al menos al 35 % del mayor. Antes salía un corte en cada frase de 8 compases.
- Dos partes seguidas con el mismo nombre se unen en una sola sección, que da un solo cue.
- "Bajón" es una parte, después de otra alta, con menos energía que la mediana del resto.

### Sección de 1 s al principio

En la primera pasada salía una sección de 1 s al principio cuando el primer "1" no está en 0:00, por ejemplo "0:00 Intro · 0:01 Verso". Corregido: ninguna sección dura menos de 8 compases. El test es `test_no_section_shorter_than_8_bars_when_the_anchor_is_late`.
