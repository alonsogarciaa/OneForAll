# OneForAll

Aplicación de escritorio para DJs en Windows. Reúne en un solo programa:

- **Buscar y descargar:** canciones y playlists de YouTube Music y SoundCloud.
- **Importar enlaces:** de Spotify, Apple Music y SoundCloud.
- **Convertir:** entre formatos de audio.
- **Biblioteca:** con etiquetas y portadas.
- **Analizar cada canción:** BPM, tonalidad (Camelot), sonoridad, forma de onda, rejilla de beats y secciones.

La interfaz está hecha con Electron y React, y el motor local con Python (FastAPI).

## Funciones

- **Buscar:** canciones, vídeos y playlists de YouTube Music, y pistas de SoundCloud.
  - Al pegar un enlace de Spotify, Apple Music o SoundCloud, sus canciones se buscan en YouTube y se descargan como una playlist.
- **Descubrir:**
  - Canciones parecidas a una de tu biblioteca, o por moods y géneros.
  - Cada una muestra su BPM y su tonalidad, calculados al vuelo, y si encaja con tu canción de referencia.
- **Biblioteca y análisis:**
  - BPM, tonalidad, LUFS, rejilla de beats editable y secciones (Intro, Verso, Subida, Estribillo/Drop, Bajón, Outro).
  - Búsqueda armónica.
- **Stems:** separación en voz, batería, bajo, guitarra, piano y resto con Demucs. La voz se puede dividir en principal y coros.
- **Mezclador de práctica:** stems en tiempo real con velocidad, tono, bucles, metrónomo y exportación de la mezcla.
- **Herramientas DJ:**
  - Copias con otro BPM o tono.
  - Exportación a Rekordbox, VirtualDJ y Serato.
- **Mejorar audio:** restauración con IA (Apollo) del audio comprimido, como copia o reemplazando el original.
- **Exportar vídeo:** MP4 con el vídeo original de YouTube, o con la portada si no hay vídeo.

## Exportar a programas DJ

Biblioteca → "Exportar a…" envía el BPM, la tonalidad, la rejilla de beats y las secciones detectadas (como cues) a:

- **Rekordbox:** escribe `OneForAll rekordbox.xml`. Se importa desde Preferencias → Avanzado → rekordbox xml.
- **VirtualDJ:** fusiona los datos con `database.xml` (antes guarda una copia de seguridad con la fecha). VirtualDJ tiene que estar cerrado.
- **Serato:** escribe las etiquetas propias de Serato dentro de los archivos MP3, FLAC y M4A. Serato las lee al cargar la pista. Los WAV se saltan.

Los formatos de Serato y VirtualDJ siguen documentación de la comunidad, no una especificación oficial.

## Desarrollo

```bash
cd engine && py -m uv sync --extra nn   # motor (Python 3.12)
npm install                              # aplicación
npm run dev                              # arrancar la aplicación
npx vitest run                           # pruebas de la interfaz
cd engine && py -m uv run pytest -q      # pruebas del motor
npm run build && npx playwright test     # pruebas de extremo a extremo
```

Instalador: `powershell -File build/fetch-runtime.ps1` y después `npm run dist`.

Banco de precisión (solo en local, descarga GiantSteps de Zenodo): `cd engine && py -m uv run python -m bench.fetch_giantsteps && py -m uv run python -m bench.run`. Los resultados están en `docs/bench/`.

La documentación de diseño de cada fase (especificaciones, planes y resúmenes) está en `docs/diseno/`.

## Componentes de terceros y licencias

| Componente | Licencia | Nota |
|---|---|---|
| madmom (código, incluido en `engine/djengine/vendor/madmom`) | BSD-2-Clause | Las extensiones compiladas se sustituyen por versiones mínimas; solo se usa la CNN de tonalidad |
| Modelo de tonalidad de madmom (`models/key/2018/key_cnn.pkl`) | CC BY-NC-SA 4.0 | **Solo uso no comercial.** Hay que sustituirlo antes de vender o distribuir comercialmente |
| DeepRhythm (CNN de tempo) | AGPL-3.0 | Válido para uso personal; distribuir la app obliga a ofrecer su código bajo AGPL |
| Demucs (código y pesos `htdemucs_6s`) | MIT | Separación de stems (Meta / Défossez et al.) |
| audio-separator | MIT | Ejecuta el modelo de karaoke de UVR |
| Modelo UVR-MDX-NET Karaoke 2 | Condiciones del autor (modelo de la comunidad UVR) | Separación de voz principal y coros; uso personal |
| Apollo (código incluido en `engine/djengine/vendor/apollo` y pesos `JusperLee/Apollo`) | CC BY-SA 4.0 | Restauración de audio comprimido (Kai Li, Yi Luo); distribuirlo exige atribución y la misma licencia |
| Signalsmith Stretch (`signalsmith-stretch`) | MIT | Tempo y tono en tiempo real en el mezclador de práctica (WASM AudioWorklet) |
| yt-dlp | Unlicense | |
| FFmpeg (compilación essentials de gyan.dev) | GPL-3.0 | Se distribuye como ejecutable aparte |
| librosa, numpy, scipy, pyloudnorm, mutagen, FastAPI | ISC / BSD / MIT | |
| Conjunto GiantSteps Key (solo para el banco de pruebas, nunca se distribuye) | CC BY-SA 4.0 | Faraldo et al.; registro de Zenodo 1095691 |

Las condiciones de uso de YouTube no permiten descargar contenido. Usa la aplicación solo con contenido que tengas derecho a descargar.
