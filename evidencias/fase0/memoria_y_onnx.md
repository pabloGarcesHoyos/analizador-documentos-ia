# Fase 0: memoria de la recuperación y cambio a ONNX

Fecha de las mediciones: 2026-11-22. Las cifras se tomaron con un script de medición que se ejecutó fuera del repositorio y no se versiona. Este archivo transcribe sus resultados. La fidelidad de la recuperación sí se puede repetir con [`app/tests/test_recuperacion.py`](../../app/tests/test_recuperacion.py).

## Entorno

- Contenedores `python:3.13-slim`: `linux/amd64` (la arquitectura de Render, emulada en un equipo Apple Silicon) y `linux/arm64` nativo.
- Modelos del corte 2: embeddings `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (revisión `e8f8c211`) y reordenador `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (revisión `1427fd65`).
- Consulta medida: la recuperación C completa sobre los 20 fragmentos del corpus 2.0, con 5 casos del conjunto anotado (D1, D4, D6, R1 y B4).

## 1. Con PyTorch

| Etapa (MB de RSS) | arm64, app completa | amd64 emulado, app completa |
|---|---|---|
| Imports de torch, sentence-transformers y BM25 | 455 | 528 |
| Más gradio, supabase, groq y mcp | 521 | 600 |
| Carga de embeddings (pico) | 924 | 965 |
| Carga del reordenador (pico) | 1.312 | 1.331 |
| Tras 5 consultas (pico) | 1.450 | 1.495 |
| Solo embeddings, tras 5 consultas | 974 | 1.066 |

Con un límite de 512 MB (`--memory=512m --memory-swap=512m`) el proceso murió por memoria (código 137) con C y también solo con embeddings. Las variantes fp16 y bf16 subieron el pico a 1.745 MB y se descartaron.

Fidelidad con PyTorch: las 51 selecciones (17 casos por 3 opciones) coinciden con `recorridos.json` del corte 2.

## 2. Con ONNX Runtime qint8

Exportaciones ONNX oficiales en las mismas revisiones. Se usa `model_qint8_arm64.onnx`, que es el mismo archivo publicado con tres nombres (ver [`app/README.md`](../../app/README.md)). Tokenizador sentencepiece compartido por los dos modelos: 641 comparaciones con `tokenizers` y 0 diferencias de ids.

| Variante | Selecciones iguales al corte 2 | Métricas agregadas |
|---|---|---|
| qint8 (elegida) | 42 de 51; los 9 cambios son de posición dentro del top 3 | Idénticas en desarrollo y reserva |
| quint8_avx2 | 39 de 51 | MRR de reserva de B y C baja de 1,0 a 0,833 |

Frente a PyTorch: coseno de la consulta con mínimo 0,967 y media 0,992; diferencia del logit del reordenador con máximo 1,22 y media 0,19 en 340 pares.

## 3. Memoria con 512 MB (amd64 emulado, app completa con Gradio y los dos MCP)

Con las reducciones finales: opciones de onnxruntime sin arena y secuenciales con 1 hilo, `MALLOC_ARENA_MAX=2`, `OMP_NUM_THREADS=1`, reordenador con `max_length=256` (el par más largo mide 89 tokens) y Filesystem MCP con el `node` del sistema.

| Configuración | ¿Sobrevive a 512 MB? | Pico del cgroup | RSS en reposo | Recuperación por consulta |
|---|---|---|---|---|
| C con los dos modelos cargados | No: muere al cargar el reordenador | 591 MB sin límite | 566 MB | 1,28 a 1,51 s |
| C bajo demanda (`C_DEMANDA`) | Sí | 497 MB | 362 MB | 1,79 a 2,15 s |
| B con embeddings cargados | Sí | 460 MB | 446 MB | 28 a 62 ms |

## 4. Render Free

El servicio corre con `RECUPERACION=C_DEMANDA`. Render Free no muestra la memoria; en Events no hubo reinicios por memoria durante las pruebas del 2026-11-22. La app escribe en el log, después de cada turno, una línea `turno ruta=… ms=… rss_mb=… pico_mb=…` para seguirla.
