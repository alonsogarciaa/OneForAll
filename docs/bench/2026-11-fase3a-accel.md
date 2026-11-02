# Aceleración de stems: ONNX + DirectML (2026-11-02)

Proveedor ONNX: DmlExecutionProvider. 5 pistas reales, 30 s cada una.

| Pista | drums | bass | other | vocals | guitar | piano | CPU s | ONNX s | × |
|---|---|---|---|---|---|---|---|---|---|
| acc1.wav | -55.4 dB | -93.9 dB | -100.1 dB | -44.1 dB | -133.8 dB | -89.6 dB | 13.1 | 1.4 | 9.30 |
| acc2.wav | -71.1 dB | -141.9 dB | -80.4 dB | -40.1 dB | -72.3 dB | -87.0 dB | 12.2 | 1.4 | 8.94 |
| acc3.wav | -55.0 dB | -83.8 dB | -88.0 dB | -62.1 dB | -108.0 dB | -140.8 dB | 12.8 | 1.4 | 8.92 |
| acc4.wav | -56.7 dB | -81.3 dB | -71.4 dB | -60.1 dB | -104.1 dB | -138.5 dB | 12.3 | 1.4 | 8.86 |
| acc5.wav | -58.0 dB | -84.0 dB | -69.0 dB | -48.5 dB | -87.8 dB | -135.8 dB | 12.3 | 1.4 | 8.90 |

Umbral (spec §6): cada stem ≥ 40 dB frente a la CPU y ≥ 1,5× más rápido.
Resultado: **CPU (no supera el umbral)**.

## Diagnóstico

Las cifras negativas de la tabla indican que la salida con DirectML es incorrecta, no ruido. Se comprobó por partes en un clip:

| Prueba | Relación señal/error |
|---|---|
| Núcleo extraído en PyTorch frente al `forward` original de Demucs | 137 dB (idéntico) |
| ONNX en CPU (onnxruntime) frente al núcleo de PyTorch | 81,7 dB (x) / 71,4 dB (xt): exportación correcta |
| ONNX con DirectML (RX 9060 XT) | −43,3 dB / −82,8 dB |
| ONNX con DirectML, sin optimizaciones de grafo | −40,7 dB / −32,4 dB |

- **Conclusión:** el proveedor DirectML de onnxruntime calcula mal este modelo en la RX 9060 XT. Como es 9 veces más rápido, merece la pena reintentarlo con futuras versiones de onnxruntime-directml o de los drivers.
- **ONNX en CPU no aporta velocidad:** 1,97 s por segmento frente a 1,91 s con PyTorch (0,97×).
- **Decisión:** la separación sigue en CPU con PyTorch.
- **Prueba anterior con torch-directml** (2026-11-02): también se desviaba (bajo 6,4 dB, guitarra 2,1 dB).
