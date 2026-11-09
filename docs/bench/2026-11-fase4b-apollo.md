# Puerta de Apollo: velocidad en CPU y escucha a ciegas (2026-11-09)

Modelo: `JusperLee/Apollo` (`pytorch_model.bin`, SHA-256 `99d9af7f…8d76`), convertido a safetensors.
Equipo: Ryzen 5 5600X, PyTorch en CPU (12 hilos; con 6 hilos va igual).
Canciones: 5 MP3 de la biblioteca bajados de YouTube. Se procesó un fragmento de 30 s desde el 30 % de cada canción.
Script: `python -m bench.apollo_gate <archivos>`. Las parejas están en `engine/bench/data/apollo/` y el orden real en `key.json`.

## Velocidad

| Pista | s de cálculo por s de audio |
|---|---|
| Quevedo - BUENAS NOCHES | 4,29 |
| Lucho RK, La Pantera - BANE | 4,16 |
| Hoke, Quevedo - ABC | 4,17 |
| Lucho RK - AIRE | 4,17 |
| Quevedo, Elvis Crespo - LA GRACIOSA | 4,15 |
| **Media** | **4,19** |

- Un trozo suelto de 10 s tarda 3,2 s por s de audio. Los fragmentos de 30 s se calculan como 4 trozos que se solapan, y ese solapamiento sube el coste.
- En una canción entera el solapamiento pesa alrededor de un 11 %, así que el coste estimado es de unos **3,5 s por s de audio**. Una canción de 3,5 min tardaría unos 12 min.
- **Umbral (spec §7.2): ≤ 3. No se cumple.** Se consulta al dueño.

## Escucha a ciegas

Hecha el 2026-11-09 por un DJ amigo del dueño. Escuchó a ciegas y eligió la versión mejorada en las 5 parejas.

| Pareja | Preferida (A/B) | ¿Es la mejorada? |
|---|---|---|
| 01 | | |
| 02 | | |
| 03 | | |
| 04 | | |
| 05 | | |

Umbral: preferir la versión mejorada en al menos 4 de las 5. **Resultado: 5 de 5, cumple.**

## DirectML

No se ha probado todavía. En la Fase 3a, con esta misma GPU (RX 9060 XT), DirectML calculó mal Demucs (−43 dB). Además, `onnxruntime-directml` choca con el `onnxruntime` de la app. Apollo usa STFT complejo, así que exportarlo a ONNX exigiría reescribir el STFT y el iSTFT como convoluciones.

## Decisión del dueño (2026-11-09)

Se sigue con la CPU sola, aunque tarde unos 12 min por canción. Las canciones se procesan en cola y en segundo plano. No se prueba DirectML en esta fase.
