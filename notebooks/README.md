# Notebooks de los cortes anteriores

Se conservan tal como se entregaron o ejecutaron, sin cambios en su código. La aplicación de `app/` extrae y adapta su lógica (ver la tabla de procedencia en [`app/README.md`](../app/README.md)).

| Notebook | Corte | Qué contiene | Salidas | Evidencia que respalda sus números |
|---|---|---|---|---|
| Corte 1 | 1 | Clasificador `analizador_v3`, su contrato y la consulta de estado. | | Pendiente: el notebook del corte 1 todavía no está en el repositorio. Sus casos se conservan como regresión en `app/tests/test_regresion_corte1.py`. |
| [`Clase_09_Demo_Colab_Mejora_Evaluacion_RAG.ipynb`](Clase_09_Demo_Colab_Mejora_Evaluacion_RAG.ipynb) | 2 (entregado) | Notebook de la Clase 09 con el que se entregó el corte 2: mejora y evaluación del RAG. | 11 de 14 celdas de código con salidas. | Sus propias salidas. |
| [`Corte2_AnalizadorDocumentos_RAG.ipynb`](Corte2_AnalizadorDocumentos_RAG.ipynb) | 2 (corregido, corpus 2.0) | Versión corregida del corte 2: corpus 2.0, fragmentación por párrafos, recuperación A, B y C, decisión por cobertura, generación con citas, regresión del corte 1 y pruebas negativas. | Sin salidas guardadas (0 de 29 celdas de código). | [`evidencias/corte2/corrida_2_rag_v3/`](../evidencias/corte2/corrida_2_rag_v3/): configuración, índice, métricas de recuperación, decisión, respuestas, revisión humana y trazas de esa ejecución. |
| [`Clase_11_Demo_Colab_RAG_Agente_MCP_Archivos.ipynb`](Clase_11_Demo_Colab_RAG_Agente_MCP_Archivos.ipynb) | 3 (punto de partida) | RAG, agente, MCP de estado y MCP de archivos de la Clase 11. | 8 de 10 celdas de código con salidas. | Sus propias salidas. |

En `evidencias/corte2/corrida_2_rag_v3/` se omiten dos archivos de la ejecución original: `sql/analizador_supabase_setup.sql`, reemplazado por `app/sql/`, y `evaluacion/pruebas_negativas.json`, porque contienen comentarios y caracteres que las reglas de este repositorio no admiten.

Antes de versionarlos se revisaron sus salidas y metadatos: no contienen claves, tokens, correos, rutas personales ni URL de Supabase.
