# Fase 6: instalación desde un clon limpio

Fecha: 2026-11-22. Repositorio: https://github.com/pabloGarcesHoyos/analizador-documentos-ia, commit clonado `ce7fcbd`. Equipo: macOS 26.5, Apple Silicon (arm64). Python 3.13.15.

Se siguió `app/README.md` al pie de la letra, sección "Instalación desde un clon limpio" para Linux/macOS, en una carpeta temporal vacía. `app/.env` y `app/.env.pruebas` se copiaron de los del equipo sin leerlos ni imprimirlos.

| Paso del README | Comando | Resultado observado | Estado |
|---|---|---|---|
| Clonar | `git clone https://github.com/pabloGarcesHoyos/analizador-documentos-ia` | Clonado en `ce7fcbd`. | Aprobado |
| Entorno virtual | `python3.13 -m venv .venv` | Python 3.13.15. En este equipo Python 3.13 no estaba en el PATH con ese nombre, así que se creó un acceso `python3.13` al intérprete 3.13.15 instalado. Se agregó al README una nota para ese caso. | Aprobado con nota |
| Dependencias | `.venv/bin/python -m pip install -r app/requirements.txt` | Instaladas, código de salida 0. | Aprobado |
| Plantilla de variables | `cp app/.env.ejemplo app/.env` | Copiada; después se reemplazó por el `app/.env` del equipo. | Aprobado |
| Modelos | `cd app` y `../.venv/bin/python descargar_modelos.py` | Descargó embeddings y reranker e imprimió `modelos verificados`. | Aprobado |
| Filesystem MCP | `../.venv/bin/npm ci --prefix mcp_archivos --omit=dev` | Instalado con el `npm` de `nodejs-wheel`, sin Node del sistema; 0 vulnerabilidades. | Aprobado |
| Ejecución local | `cd app` y `../.venv/bin/python app.py` | `Running on local URL: http://127.0.0.1:7860`, HTTP 200. El proceso corría desde la carpeta `app` del clon. | Aprobado |
| Uso | Inicio de sesión y "¿En qué estado está DOC-1001?" en el navegador | Respuesta con `[T1]`, entrada reactivada, página en español, sin errores de consola. En el log: `turno ruta=estado ms=4077 … pico_mb=279.7`. | Aprobado |
| Detener | Ctrl+C | La app se detuvo y liberó el puerto 7860. | Aprobado |
| Pruebas | `.venv/bin/python -m pip install -r requirements-pruebas.txt` y `.venv/bin/python -m pytest` | 497 pruebas aprobadas, 55 deseleccionadas (integración, Groq y SQL local). | Aprobado |

No se ejecutaron en este clon: el SQL y la carga del corpus (el proyecto de Supabase ya los tiene; `cargar_corpus.py` se probó con pruebas unitarias), las pruebas de integración ni la instalación en PowerShell.
