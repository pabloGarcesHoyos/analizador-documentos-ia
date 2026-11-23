# Notebooks de los cortes anteriores

Se conservan tal como se entregaron o ejecutaron, sin cambios en su código. La aplicación de `app/` extrae y adapta su lógica (ver la tabla de procedencia en [`app/README.md`](../app/README.md)).

| Notebook | Corte | Qué contiene | Salidas | Evidencia que respalda sus números |
|---|---|---|---|---|
| [`Clase_03_Demo_Groq.ipynb`](Clase_03_Demo_Groq.ipynb) | 1 | Clase 03: contrato `AnalisisDocumento`, prompt `system_v1` y primeras llamadas a Groq con salida estructurada. | 5 de 10 celdas de código con salidas. | Sus propias salidas. |
| [`Clase_04_Analizador_Documentos_Herramientas.ipynb`](Clase_04_Analizador_Documentos_Herramientas.ipynb) | 1 (entregado) | Prototipo entregado en el corte 1: clasificación con `system_v2`, herramienta de solo lectura `consultar_estado_documento`, matriz de 11 casos, pruebas negativas y control del límite de tasa. | 12 de 13 celdas de código con salidas. | [`evidencias/corte1/clase04_groq/`](../evidencias/corte1/clase04_groq/) (llamadas reales del 2026-09-20) y [`evidencias/corte1/clase04_mock/`](../evidencias/corte1/clase04_mock/) (respuestas escritas por el equipo). Sus casos siguen como regresión en `app/tests/test_regresion_corte1.py`. |
| [`Clase_09_Demo_Colab_Mejora_Evaluacion_RAG.ipynb`](Clase_09_Demo_Colab_Mejora_Evaluacion_RAG.ipynb) | 2 (entregado) | Notebook de la Clase 09 con el que se entregó el corte 2: mejora y evaluación del RAG. | 11 de 14 celdas de código con salidas. | Sus propias salidas. |
| [`Corte2_AnalizadorDocumentos_RAG.ipynb`](Corte2_AnalizadorDocumentos_RAG.ipynb) | 2 (corregido, corpus 2.0) | Versión corregida del corte 2: corpus 2.0, fragmentación por párrafos, recuperación A, B y C, decisión por cobertura, generación con citas, regresión del corte 1 y pruebas negativas. | Sin salidas guardadas (0 de 29 celdas de código). | [`evidencias/corte2/corrida_2_rag_v3/`](../evidencias/corte2/corrida_2_rag_v3/): configuración, índice, métricas de recuperación, decisión, respuestas, revisión humana y trazas de esa ejecución. |
| [`Clase_11_Demo_Colab_RAG_Agente_MCP_Archivos.ipynb`](Clase_11_Demo_Colab_RAG_Agente_MCP_Archivos.ipynb) | 3 (punto de partida) | RAG, agente, MCP de estado y MCP de archivos de la Clase 11. | 8 de 10 celdas de código con salidas. | Sus propias salidas. |

En `evidencias/corte2/corrida_2_rag_v3/` se omiten dos archivos de la ejecución original: `sql/analizador_supabase_setup.sql`, reemplazado por `app/sql/`, y `evaluacion/pruebas_negativas.json`, porque contienen comentarios y caracteres que las reglas de este repositorio no admiten.

En `evidencias/corte1/` se omite `bitacora.json` de cada ejecución, por la misma razón.

Antes de versionarlos se revisaron sus salidas y metadatos: no contienen claves, tokens, correos, rutas personales ni URL de Supabase.
