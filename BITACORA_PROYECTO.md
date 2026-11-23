# Bitácora del proyecto: Analizador de Documentos

Documentación integral de los tres cortes del proyecto del curso Inteligencia Artificial Generativa y Sistemas Inteligentes, EAM 2026-II. Profesor: Robert Garcia Rey. Equipo: Pablo Garcés Hoyos y Axel Dereck Gutiérrez.

Este documento cuenta cómo evolucionó el proyecto, qué se decidió, qué se probó y qué falló. Las instrucciones de instalación y despliegue están en [`app/README.md`](app/README.md). Cada cifra lleva el archivo que la respalda; lo que no tiene archivo se dice.

## Índice

1. [Problema, usuarios, objetivos y alcance](#1-problema-usuarios-objetivos-y-alcance)
2. [Arquitectura final y recorrido de una solicitud](#2-arquitectura-final-y-recorrido-de-una-solicitud)
3. [Decisiones técnicas](#3-decisiones-técnicas)
4. [Experimentos y pruebas de los tres cortes](#4-experimentos-y-pruebas-de-los-tres-cortes)
5. [Errores, limitaciones y correcciones](#5-errores-limitaciones-y-correcciones)
6. [Aportes de cada integrante](#6-aportes-de-cada-integrante)
7. [Uso de asistentes](#7-uso-de-asistentes)
8. [Funcionamiento final y conclusiones](#8-funcionamiento-final-y-conclusiones)

Fuentes usadas: las bitácoras de las clases 02 a 04 y 06 a 11; el README, las evidencias y la presentación del corte 1; el notebook y la presentación entregados en el corte 2; la versión corregida del corte 2; el plan de trabajo del corte 3 y la carpeta [`evidencias/`](evidencias/). Los notebooks de las clases 02, 06, 07 y 08 no están en el repositorio: lo que viene de esas clases se respalda solo con su bitácora.

## 1. Problema, usuarios, objetivos y alcance

### Problema

Un área administrativa recibe facturas, contratos y documentos de identificación. Quien los revisa necesita saber tres cosas: qué exige cada política, en qué estado va un trámite y si un documento entregado cumple lo mínimo. Un modelo de lenguaje sin control inventa requisitos, plazos y estados. El proyecto busca que cada respuesta salga de una fuente verificable: un pasaje del corpus de políticas o un registro consultado.

### Usuarios

Personas del área con una cuenta en Supabase Auth autorizada como lectora del corpus. Cada una tiene su propio historial de conversaciones, que nadie más puede leer.

### Objetivos

- Responder preguntas de políticas citando el pasaje que respalda cada frase.
- Informar el estado de un documento (`DOC-XXXX`) o una solicitud (`SOL-XXXX`) desde un registro, sin que el modelo lo redacte.
- Clasificar el texto de un documento e indicar qué campos faltan.
- Distinguir la falta de evidencia de un error técnico.
- Escribir un informe solo cuando el usuario lo aprueba.

### Alcance

El analizador solo consulta. No registra, aprueba, firma, modifica, cancela ni elimina nada; esas peticiones se rechazan y se remiten a revisión humana. El corpus y el registro son ficticios y no contienen datos personales reales.

### Cambios respecto de la propuesta inicial

| Etapa | Qué era el proyecto | Por qué cambió | Fuente |
|---|---|---|---|
| Clase 02 (2026-09-02) | Analizador de contratos y documentos legales: responder preguntas sobre un fragmento de contrato y abstenerse si el dato no aparece. | El curso pasó a salidas estructuradas y herramientas; el alcance se amplió a cuatro tipos de documento. | Bitácora C02 |
| Corte 1 (entrega 2026-09-20) | Clasificador de documentos (`factura`, `contrato`, `identificacion`, `desconocido`) con contrato de salida validado y una herramienta de solo lectura para consultar el estado de `DOC-XXXX`. | El corte 2 pidió recuperación sobre un corpus (RAG). | [`notebooks/Clase_04_Analizador_Documentos_Herramientas.ipynb`](notebooks/Clase_04_Analizador_Documentos_Herramientas.ipynb), [presentación del corte 1](evidencias/corte1/presentacion/Corte1_AnalizadorDocumentos.pptx) |
| Corte 2 (entrega 2026-11-02) | Se conserva el clasificador y se agrega RAG sobre políticas de facturación, contratos e identificación, con embeddings en Supabase y una mejora de recuperación elegida por evaluación. | El corte 3 pidió una aplicación web con historial por usuario. | [`notebooks/Clase_09_Demo_Colab_Mejora_Evaluacion_RAG.ipynb`](notebooks/Clase_09_Demo_Colab_Mejora_Evaluacion_RAG.ipynb), [`notebooks/Corte2_AnalizadorDocumentos_RAG.ipynb`](notebooks/Corte2_AnalizadorDocumentos_RAG.ipynb) |
| Corte 3 (2026-11-22) | Aplicación Gradio con inicio de sesión, historial en Supabase con RLS, MCP propio de estado, informe con Filesystem MCP y aprobación del usuario. | | [`app/`](app/) |

## 2. Arquitectura final y recorrido de una solicitud

### Componentes

| Componente | Archivo | Notebook o corte de origen |
|---|---|---|
| Interfaz: sesión, lista de conversaciones, chat con fuentes y consultas, aprobación del informe | [`app/app.py`](app/app.py) | Clase 11, puntos 7 y 8, convertidos en eventos de Gradio |
| Enrutador por reglas, rutas, contratos, validación de citas, cliente de Groq con control de cupo, clientes MCP, informe | [`app/sistema.py`](app/sistema.py) | Clase 11, puntos 4 a 6; corte 2, secciones 1, 9 y 10; corte 1 (`AnalisisDocumento`, `validar_y_decidir_clasificacion`) |
| Recuperación híbrida con reordenamiento, en ONNX | [`app/recuperacion.py`](app/recuperacion.py) | Corte 2, sección 7 |
| Sesión, conversaciones, mensajes y decisiones de informe en Supabase | [`app/almacenamiento.py`](app/almacenamiento.py) | Nuevo; reemplaza `MEMORIA` de la Clase 11 |
| MCP propio de estado, solo lectura, por stdio | [`app/servidor_mcp.py`](app/servidor_mcp.py) | Clase 11, punto 4; registro del corte 2 |
| Filesystem MCP para el informe | [`app/mcp_archivos/`](app/mcp_archivos/) | Clase 11, punto 4.b |
| Carga única del corpus | [`app/cargar_corpus.py`](app/cargar_corpus.py) | Corte 2, secciones 3, 4 y 6 |
| Esquema, RLS y funciones | [`app/sql/`](app/sql/) | Corte 2 (corpus) y nuevo (historial e informes) |
| Corpus ficticio 2.0 | [`app/corpus/`](app/corpus/) | Corte 2, versión corregida |
| Pruebas | [`app/tests/`](app/tests/) | Nuevo; la regresión usa los 11 casos del corte 1 |

### Recorrido de una solicitud

1. El usuario inicia sesión. La sesión de Gradio guarda solo sus tokens, en el servidor.
2. Escribe una pregunta. Antes de cada operación se valida el token con `auth.get_user`.
3. El enrutador elige la ruta por reglas, sin modelo: `rechazo`, `estado`, `mixta`, `pide_codigo`, `rag`, `documento` o `libre`.
4. Según la ruta:
   - `estado`: el MCP propio consulta el código y el programa escribe la frase con su etiqueta `[T#]`;
   - `rag`: se recuperan 3 pasajes y el modelo responde con el contrato rag_v5; el programa valida cada cita `[F#]`;
   - `mixta`: las dos cosas, y el modelo nunca recibe ni escribe el valor del estado;
   - `documento`: el clasificador del corte 1 (`analizador_v3`);
   - `libre`: una llamada al modelo decide entre aclarar, rechazar o buscar.
5. Si el usuario pidió un informe y hay fuentes, la interfaz muestra la propuesta y espera Aprobar o Rechazar.
6. El turno completo se guarda en Supabase con su estado, fuentes, consultas y traza.

El detalle de cada paso está en [`app/README.md`](app/README.md), sección "Recorrido de una pregunta".

## 3. Decisiones técnicas

### Modelo generativo

| Decisión | Justificación | Alternativa descartada | Fuente |
|---|---|---|---|
| Clase 02: `gemma4:e2b` con Ollama en Colab con GPU T4, `temperature=0.0` y `seed=42` | Medir el efecto de la temperatura con una configuración reproducible. Las tres temperaturas dieron respuestas idénticas, así que se conservó 0.0. | `temperature=0.7` | Bitácora C02 |
| Desde la Clase 03: `openai/gpt-oss-20b` en Groq | Groq garantiza la forma del JSON con `strict: true` (Structured Outputs); no exige GPU propia, así que el mismo modelo sirve en Colab y en un servidor web. Se conservó en los tres cortes para poder comparar resultados. | Seguir con Ollama: exige levantar el modelo en cada sesión y no corre en un alojamiento gratuito de 512 MB. | [`notebooks/Clase_03_Demo_Groq.ipynb`](notebooks/Clase_03_Demo_Groq.ipynb); [`evidencias/corte1/clase04_groq/configuracion.json`](evidencias/corte1/clase04_groq/configuracion.json) |
| Se acepta que el modelo no es determinista | Groq no expone semilla para este modelo. Con `temperature=0.0`, dos corridas del corte 1 dieron 8 de 11 fallando casos distintos. La reproducibilidad de la Clase 02 no se transfiere a una API. | Suponer determinismo y evaluar con una sola corrida | README y bitácora C04 del corte 1 |
| `max_completion_tokens` 3000 y un reintento solo ante `json_validate_failed` | El modelo gasta tokens de razonamiento del mismo presupuesto; con presupuestos bajos la respuesta llega vacía. | 1400 (corte 1) y 1024 o 700 (primeras versiones del corte 3) | Bitácora C03; [`app/sistema.py`](app/sistema.py) |

### Prompts y su versionado

| Versión | Dónde | Qué cambió y por qué | Estado |
|---|---|---|---|
| system_v0 | Clase 02 | Así se llama aquí a la instrucción de la Clase 02, que no tenía versión. Exigía abstención explícita. Pedía a la vez la frase de abstención y citar la cláusula, y el modelo repitió la frase. | Retirada |
| system_v1 | Clase 03 | Contrato de 7 campos, contenido delimitado por `<texto_documento>` y tratado como dato. | Base de v2 |
| system_v2 y herramienta_v2_tres_casos | Clase 04 | Reglas de seguimiento: las consultas se clasifican como `desconocido`. El prompt de la herramienta separa primero tres intenciones, porque la v1 respondía "no se encontró un código" ante una factura. | Retiradas |
| analizador_v3 (archivo `system_v3.md`) | Corte 2 corregido | Resumen de máximo 200 caracteres, porque `malicioso_01` fallaba por longitud (mejora pendiente 3 del corte 1). | Vigente en la ruta `documento` |
| rag_v1 a rag_v4 | Clase 08 a corte 2 corregido | v2: ejemplos de formato y reintento con la causa, tras 25 de 34 respuestas en `ERROR_VALIDACION`. v3: corrida 2. v4: no combinar pasajes, no añadir requisitos, citar cada frase, tras las afirmaciones sin respaldo de C. | Retiradas |
| agente_v1 a agente_v3 | Corte 3 | Agente libre de la Clase 11 con las reglas de rag_v4. Tres rondas (sección 5.3). | Reemplazado por el flujo |
| rag_v5 | Corte 3 | Contrato por frases: el modelo devuelve cada frase sin etiquetas con su lista de citas, y el programa arma el texto. | Vigente |
| enrutador_v2 | Corte 3 | Prompt de la ruta libre. Presenta al asistente como el Analizador de Documentos y no menciona su funcionamiento interno, porque la v1 se presentaba como "el enrutador". | Vigente |

Las versiones vigentes se leen en [`app/sistema.py`](app/sistema.py) (`FLUJO_VERSION`, `PROMPT_RAG_VERSION`, `PROMPT_ENRUTADOR_VERSION`) y quedan en la traza de cada mensaje.

### Contratos Pydantic

| Decisión | Justificación | Alternativa descartada |
|---|---|---|
| Dos capas: esquema estricto en Groq y validación Pydantic con `extra="forbid"` en la aplicación | El esquema de Groq no expresa longitudes ni rangos. En el corte 1, `malicioso_01` pasó el esquema del proveedor y lo rechazó Pydantic por longitud. | Confiar solo en el proveedor |
| Revisión humana se evalúa antes que aclaración | Si ambas aplican, prevalece la más restrictiva. | Orden inverso |
| Se retira el umbral `confianza < 0.60` | La confianza declarada no está calibrada: 0.2 en una inyección detectada y 0.9 en una receta de cocina. Detuvo consultas válidas. | Mantener el umbral |
| Las citas se validan y nunca se agregan | Una cita debe sostener una frase. En el corte 2 entregado, el validador agregaba las etiquetas que faltaban (sección 5.1). | Completar citas en el programa |

### Corpus y fragmentación

| Versión | Contenido | Fragmentación | Resultado | Fuente |
|---|---|---|---|---|
| Corpus 1.0 (corte 2 entregado) | 2 documentos: `politicas_facturacion.md` y `gestion_contratos_identificacion.md` | Por párrafos con 80 tokens incluido el encabezado de sección (Clase 07): 9 fragmentos en `clase08_fragmentos` | Un fragmento cortado en "...el monto esta incompleto, el sistema" | [`notebooks/Clase_09_Demo_Colab_Mejora_Evaluacion_RAG.ipynb`](notebooks/Clase_09_Demo_Colab_Mejora_Evaluacion_RAG.ipynb), celdas 5, 7 y 25 |
| Corpus 2.0 (vigente) | 4 documentos, versión `2.0-2026-10`, con cada regla junto a su condición y su consecuencia | Por párrafos, con un presupuesto de 120 tokens que solo divide los párrafos que no caben: 20 fragmentos sin unidades partidas | Con 80 tokens se partían reglas; con ventanas fijas de 60 tokens se partían unidades anotadas | [`evidencias/corte2/corrida_2_rag_v3/indice/comparacion_estrategias.json`](evidencias/corte2/corrida_2_rag_v3/indice/comparacion_estrategias.json); bitácora C10 |

El corpus 2.0 tiene el identificador `analizador_documental_v2-057b729f44ae`, y `app/cargar_corpus.py` lo reproduce exactamente.

### Recuperación A, B y C

- **A:** búsqueda semántica con embeddings `paraphrase-multilingual-MiniLM-L12-v2` y similitud coseno.
- **B:** híbrida, que suma BM25 (búsqueda por palabras) y la semántica mediante RRF (fusión por posición en cada lista, c = 60).
- **C:** B más un reordenador (cross-encoder `mmarco-mMiniLMv2-L12-H384-v1`) que puntúa cada par de pregunta y pasaje y deja los 3 mejores de 10 candidatos.

Decisión vigente: **C**, según la regla escrita antes de ver los datos: cobertura, luego MRR, luego Recall@3 y luego la opción más simple ([`evidencias/corte2/corrida_2_rag_v3/evaluacion/decision.json`](evidencias/corte2/corrida_2_rag_v3/evaluacion/decision.json)).

| Configuración | Cobertura (desarrollo) | MRR (desarrollo) | Recall@3 (desarrollo) | Latencia mediana en Colab |
|---|---|---|---|---|
| A | 0,875 | 0,875 | 0,875 | 136 ms |
| B | 0,812 | 0,792 | 0,812 | 137 ms |
| C | 0,938 | 0,938 | 0,938 | 865 ms |

Alternativa descartada: A, más rápida pero que pierde reglas en D5 y R1. La decisión del corte 2 entregado, que también eligió C, no tenía ventaja medida (sección 5.1).

### ONNX en lugar de PyTorch

| Decisión | Justificación | Alternativa descartada | Fuente |
|---|---|---|---|
| Los mismos modelos del corte 2 en ONNX qint8 con ONNX Runtime y un tokenizador sentencepiece, sin PyTorch | Con PyTorch la app llega a unos 1.450 MB y muere con 512 MB, incluso solo con embeddings. Con ONNX qint8 las métricas agregadas del corte 2 son idénticas y 42 de 51 selecciones quedan en el mismo orden. | Plan de pago con 2 GB; PyTorch en fp16 o bf16, con un pico más alto (1.745 MB) | [`evidencias/fase0/memoria_y_onnx.md`](evidencias/fase0/memoria_y_onnx.md); [`app/tests/test_recuperacion.py`](app/tests/test_recuperacion.py) |
| C bajo demanda (`C_DEMANDA`): cada modelo se carga durante la consulta y se libera al terminar | C con los dos modelos residentes muere al cargar el reordenador. C bajo demanda tiene un pico de 497 MB y conserva la recuperación elegida. | B residente (460 MB), que abandona el reordenador; queda como respaldo con `RECUPERACION=B` | [`evidencias/fase0/memoria_y_onnx.md`](evidencias/fase0/memoria_y_onnx.md) |

### Agente libre frente a flujo predefinido

| Decisión | Justificación | Alternativa descartada |
|---|---|---|
| Flujo predefinido: un enrutador por reglas elige la ruta y el modelo solo redacta | Tres rondas del agente libre terminaron con 5, 7 y 8 de 11 en la regresión, y con 3 de 6 y 2 de 6 en las reservas. Sus fallas no se corrigieron con el prompt: terminar sin consultar un código presente, redactar estados, citas sin corchetes. La ruta se puede decidir con reglas, como ya hacía el corte 2. El flujo dio 10 de 11 en la regresión con unos 3.000 tokens, frente a 20.805 del agente_v3. | Agente libre de la Clase 11 (`agente_v3`, commit `3264be1`) |
| El programa escribe las frases de estado con su `[T#]` | Es la única forma de garantizar que el estado mostrado es el del registro. No agrega citas a frases del modelo: la frase entera la genera el programa desde el dato validado. | Dejar que el modelo redacte el estado |

### MCP propio y Filesystem MCP

| Decisión | Justificación | Alternativa descartada |
|---|---|---|
| MCP propio `consultar_estado_solicitud`, solo lectura, por stdio, con el patrón del código en el esquema publicado | Herramienta del dominio, sin puertos ni autenticación extra. El esquema de la Clase 11 no publicaba el patrón. | Endpoint HTTP propio |
| Un solo registro con `DOC-1001` a `DOC-1003` (corte 2) y `SOL-1001` a `SOL-1002` (Clase 11), cada uno con su `fuente` | De los registros del corte 2 dependen las 11 pruebas de regresión del corte 1. | Los estados de `DOC` de la Clase 11, que no coincidían |
| Filesystem MCP 2.2.0 con una sola carpeta permitida y solo la operación de escritura | El informe es una acción sensible: la interfaz muestra contenido y destino, el usuario aprueba con un botón, el código comprueba la aprobación y la huella, y se registra una sola decisión por mensaje. | Escribir el informe dentro del ciclo del agente, como en la Clase 11 |

### Sesiones, RLS e historial

| Decisión | Justificación | Alternativa descartada |
|---|---|---|
| Cada sesión de Gradio guarda solo sus tokens; cada operación crea un cliente con el token del usuario y lo valida con `auth.get_user` | Un cliente global autenticado mezclaría usuarios. | Un cliente compartido o una clave administrativa |
| RLS en `conversaciones`, `mensajes` y `acciones_informe`, con llave foránea `(conversacion_id, usuario_id)` | Conocer un UUID ajeno no da acceso a leer ni a insertar. | Filtrar solo en el código |
| El corpus lo leen su dueño y los usuarios de `lectores_corpus`, con una función de búsqueda `security invoker` | La función del corte 2 filtraba por `auth.uid()` y devolvía cero filas a cualquier otro usuario. | Abrir el corpus a todos o desactivar RLS |
| Se guarda la conversación completa y al modelo van los últimos 4 turnos | Persistir y elegir contexto son decisiones distintas; 4 turnos acotan tokens y cupo. | Enviar todo el historial |
| Middleware que cierra la API directa de Gradio y validador de sesión en cada evento | `api_visibility="private"` solo oculta la documentación; el servidor seguía aceptando llamadas. | Confiar en `api_visibility` |

## 4. Experimentos y pruebas de los tres cortes

Estados: **cumple**, **parcial** o **no cumple** frente a lo esperado. Se incluyen las corridas fallidas.

### Corte 1

| Fecha | Configuración o versión | Esperado | Observado | Estado | Evidencia |
|---|---|---|---|---|---|
| 2026-09-02 | Clase 02, `gemma4:e2b`, 3 temperaturas y 2 preguntas | P1 cita la cláusula; P2 se abstiene | P1 correcta y P2 abstenida en las 6 llamadas, con texto idéntico en las tres temperaturas. La abstención salió duplicada. | parcial | Bitácora C02; el notebook de la Clase 02 no está en el repositorio |
| 2026-09-09 | Clase 03, system_v1, 5 casos con Groq | Contrato válido en los 5 y `ERROR_FORMATO` en la prueba negativa | 5 de 5 válidos; prueba negativa rechazada. Lo esperado de cada caso no se escribió antes. | parcial | [`notebooks/Clase_03_Demo_Groq.ipynb`](notebooks/Clase_03_Demo_Groq.ipynb) |
| 2026-09 | Clase 04 en modo groq sin control de cupo | 11 casos | Desde el quinto caso, todos rebotaron con 429 | no cumple | Bitácora C04 |
| 2026-09 | Clase 04 en modo groq, primera corrida completa | 11 de 11 | 8 de 11; fallaron los casos 7, 9 y 11 | parcial | Bitácora C04 |
| 2026-09-20 | Clase 04 en modo groq, corrida entregada | 11 de 11 | 8 de 11; fallaron `normal_01`, `ambiguo_01` y `malicioso_01`. Pruebas negativas: 6 de 6. Latencia media de 957 ms sin contar 115 s de pausas por cupo. | parcial | [`evidencias/corte1/clase04_groq/`](evidencias/corte1/clase04_groq/) |
| 2026-09-20 | Clase 04 en modo mock | 11 de 11 | 11 de 11. Solo comprueba las reglas del programa, no al modelo. | cumple | [`evidencias/corte1/clase04_mock/`](evidencias/corte1/clase04_mock/) |

### Corte 2

| Fecha | Configuración o versión | Esperado | Observado | Estado | Evidencia |
|---|---|---|---|---|---|
| 2026-10-06 | Clase 06: embeddings `paraphrase-multilingual-MiniLM-L12-v2` sobre un corpus de prueba de 5 pasajes (D1 a D5) | La búsqueda semántica encuentra lo que la literal no | Búsqueda literal por "recibo": lista vacía. Búsqueda semántica: D1 en primer lugar, con similitud 0,451. Una pregunta fuera de cobertura también devuelve candidatos con puntaje, así que la similitud no basta para saber si hay evidencia. | cumple | Bitácora C06 |
| 2026-10-07 | Clase 07: corpus 1.0, ventanas fijas frente a párrafos, 80 tokens por fragmento con encabezado | Ningún fragmento pasa del límite del modelo (128 tokens) y el índice se recarga igual | Máximo de 78 tokens; recarga del índice comprobada con aserciones. Se eligió la fragmentación por párrafos. | cumple | Bitácora C07 |
| 2026-10-14 | Clase 08: corpus 1.0 en Supabase (`clase08_fragmentos`), búsqueda por RPC y generación con Groq y el contrato `RespuestaRAG` (rag_v1) | Respuesta con citas validadas | Primera ejecución: error técnico, porque el modelo agrupaba citas (`[F1, F3]`) o escribía etiquetas que no ponía en la lista. Con reglas de citación individual en el prompt, la respuesta pasó la validación. La persistencia se comprobó desde un segundo cliente. | parcial | Bitácora C08 |
| 2026-10-20 (entregado el 2026-11-02) | Clase 09: corpus 1.0, 8 casos, A, B y C | Una configuración con ventaja medida | A, B y C con los mismos valores en desarrollo y reserva: Recall@3 1,0, MRR 1,0 y cobertura 1,0. Medianas en desarrollo: A 518,9 ms, B 519,4 ms y C 1.343,6 ms. | no cumple | [`notebooks/Clase_09_Demo_Colab_Mejora_Evaluacion_RAG.ipynb`](notebooks/Clase_09_Demo_Colab_Mejora_Evaluacion_RAG.ipynb), celdas 17 y 19 |
| 2026-10-24 | Corrida 1: corpus 2.0, 17 casos, rag_v2 | Respuestas validadas en A y C | Recuperación: C elegida por la regla. Generación: 25 de 34 respuestas en `ERROR_VALIDACION`. Regresión del corte 1: 8 de 11. | no cumple | [`evidencias/corte2/corrida_1_rag_v2/`](evidencias/corte2/corrida_1_rag_v2/) |
| 2026-10-24 | Corrida 2: corpus 2.0, 17 casos, rag_v3 | Estado aceptable y respuestas fieles | Estado aceptable: A 15 de 17 y C 17 de 17, sin errores técnicos. Revisión humana: A fiel en 17 de 17 y C en 14 de 17 (D1, D6 y R1 con afirmaciones sin respaldo). Regresión: 9 de 11. | parcial | [`evidencias/corte2/corrida_2_rag_v3/`](evidencias/corte2/corrida_2_rag_v3/), [`revision_humana_corrida_2.json`](evidencias/corte2/corrida_2_rag_v3/revision_humana_corrida_2.json) |
| 2026-10-24 | rag_v4 en la versión corregida | C fiel | La bitácora C10 registra C fiel en 16 de 17 y regresión de 11 de 11. No hay archivo con esa corrida, así que esas cifras no se usan. | sin evidencia | Bitácora C10 |
| 2026-11-11 | Clase 11: agente con RAG B, MCP de estado y Filesystem MCP | Recorrido buscar, consultar, guardar y responder | Llegó a `RESPONDER` en 4 pasos. Se encontraron defectos en el notebook (sección 5.2). | parcial | [`notebooks/Clase_11_Demo_Colab_RAG_Agente_MCP_Archivos.ipynb`](notebooks/Clase_11_Demo_Colab_RAG_Agente_MCP_Archivos.ipynb) |

### Corte 3

Todas las corridas son del 2026-11-22, con `openai/gpt-oss-20b` y recuperación `C_DEMANDA`. Cada reserva se escribió y versionó antes de cambiar el prompt, y se corrió una sola vez.

| Configuración o versión | Esperado | Observado | Estado | Evidencia |
|---|---|---|---|---|
| Memoria con PyTorch y 512 MB | La app cabe | Pico de unos 1.450 a 1.500 MB; muere con 512 MB | no cumple | [`evidencias/fase0/memoria_y_onnx.md`](evidencias/fase0/memoria_y_onnx.md) |
| ONNX qint8 frente al corte 2 | Mismas métricas agregadas | Idénticas; 42 de 51 selecciones en el mismo orden | cumple | [`evidencias/fase0/memoria_y_onnx.md`](evidencias/fase0/memoria_y_onnx.md), [`app/tests/test_recuperacion.py`](app/tests/test_recuperacion.py) |
| SQL y almacenamiento contra Supabase real | Aislamiento entre dos usuarios | 8 de 8 | cumple | [`evidencias/fase1/pruebas_integracion.md`](evidencias/fase1/pruebas_integracion.md) |
| agente_v1, corrida inicial | 11 de 11 | 1 de 11, por fallas de infraestructura (cliente reutilizado entre bucles de eventos y 429 sin control de cupo) | no cumple | [`evidencias/fase2/regresion_corte1.md`](evidencias/fase2/regresion_corte1.md) |
| agente_v1, corridas 1 y 2 | 11 de 11 | 5 de 11 en cada una | no cumple | [corrida 1](evidencias/fase2/regresion_corte1_20261122T1711_corrida1.md), [corrida 2](evidencias/fase2/regresion_corte1_20261122T1721_corrida2.md) |
| agente_v2 | 11 de 11 y reserva de 6 | Regresión 7 de 11; reserva 3 de 6 | no cumple | [regresión](evidencias/fase2/regresion_corte1_20261122T1736_agente_v2.md), [reserva](evidencias/fase2/reserva_agente_20261122T1743_agente_v2.md) |
| agente_v3 | 11 de 11 y reserva 2 de 6 casos | Regresión 8 de 11; reserva 2: 2 de 6 | no cumple | [regresión](evidencias/fase2/regresion_corte1_20261122T1753_agente_v3.md), [reserva 2](evidencias/fase2/reserva2_agente_20261122T1801_agente_v3.md) |
| flujo_v1 | 11 de 11 y reserva 3 de 6 casos | Regresión 10 de 11 (falla `normal_01`), 2.941 tokens; reserva 3: 6 de 6 | parcial | [regresión](evidencias/fase2/regresion_corte1_20261122T1824_flujo_v1.md), [reserva 3](evidencias/fase2/reserva3_flujo_20261122T1827_flujo_v1.md) |
| flujo_v2 (una etiqueta por frase) | Sin cambios en lo que ya pasaba | Regresión 10 de 11; reserva 3: **5 de 6, resultado oficial**. `reserva3_registrar_factura` pasa a `ERROR_VALIDACION`. | parcial | [regresión](evidencias/fase2/regresion_corte1_20261122T1858_flujo_v2.md), [reserva 3](evidencias/fase2/reserva3_flujo_20261122T1901_flujo_v2.md) |
| flujo_v3 (reintento con todas las reglas) | `reserva3_registrar_factura` respondida | Sigue en `ERROR_VALIDACION` | no cumple | [evidencia](evidencias/fase2/reserva3_registrar_factura_20261122T1912_flujo_v3.md) |
| flujo_v4 con rag_v5 | Sin regresiones | Regresión 10 de 11; reserva 3: 6 de 6, ya no ciega | parcial | [regresión](evidencias/fase2/regresion_corte1_20261122T2027_flujo_v4.md), [reserva 3](evidencias/fase2/reserva3_flujo_20261122T2030_flujo_v4.md) |
| Interfaz en el navegador, corrida 1 | 15 de 15 pasos | 14 de 15; el paso 2 falló por un defecto del script | parcial | [`evidencias/fase3/prueba_interfaz.md`](evidencias/fase3/prueba_interfaz.md) |
| Interfaz, corrida 2 | 15 de 15 | 10 de 15; la pregunta mixta terminó en `ERROR_VALIDACION` (motivó rag_v5) y otros pasos fallaron por esperas fijas del script | no cumple | [`evidencias/fase3/prueba_interfaz.md`](evidencias/fase3/prueba_interfaz.md) |
| Interfaz, corrida 3 | 15 de 15 | 15 de 15 | cumple | [`evidencias/fase3/prueba_interfaz.md`](evidencias/fase3/prueba_interfaz.md) |
| URL pública, commit `1ce46c5` | Sin evidencia, reinicio, aislamiento y falla técnica | 5 de 5 | cumple | [`evidencias/fase4/pruebas_url_publica.md`](evidencias/fase4/pruebas_url_publica.md) |
| Instalación desde un clon limpio, commit `ce7fcbd` | Arranque siguiendo el README | Arranca; las 497 pruebas sin servicios externos pasan. Hizo falta un acceso `python3.13`, que se agregó al README. | cumple | [`evidencias/fase6/clon_limpio.md`](evidencias/fase6/clon_limpio.md) |
| Prueba ciega: 6 preguntas propias de Axel, ejecutadas el 2026-11-23 en la URL pública con su usuario (commit desplegado `4a12b75`) | Lo esperado por Axel, versionado antes en `9b81c9a` | 5 aprobadas (una con observación) y 1 fallida. Falló "¿Me puedes decir cómo va el trámite SOL-2048?": se esperaba la ruta estado sin modelo y salió mixta con 1 llamada, porque el enrutador toma "puedes" como señal de pregunta de políticas; el dato del registro fue correcto. Aprobada con observación, por decisión de Axel: "Quiero que apruebes y registres una factura nueva" terminó en rechazo sin herramientas y con el rótulo de que el analizador solo consulta, pero por la ruta libre con 1 llamada y con un texto genérico. | parcial | [`evidencias/fase4/preguntas_propias_axel.md`](evidencias/fase4/preguntas_propias_axel.md) |

## 5. Errores, limitaciones y correcciones

### 5.1 Corte 2 tal como se entregó el 2026-11-02

El corte 2 se entregó con el notebook de la Clase 09 y una presentación en PDF de 5 páginas.

- **Elección sin ventaja medida.** Con 9 fragmentos y 8 casos, A, B y C dieron valores idénticos (celdas 17 y 19). Con 10 candidatos, cada método recibía el corpus completo, así que el conjunto no podía distinguirlos. Se eligió C sin una regla de desempate escrita antes (celda 19).
- **Validador que agregaba citas.** `validar_respuesta` añadía al final del texto las etiquetas que faltaban, en lugar de rechazar la salida (celda 23). La bitácora C09 lo registró como decisión.
- **Fragmento cortado y revisión fija.** `parrafos:5` terminaba en "...el monto esta incompleto, el sistema". A completó la frase sin pasaje que la respaldara. La revisión manual asignó `True` a todos los criterios de las dos opciones con una sola justificación (celda 25).
- **Cifras de la presentación sin origen en el notebook.** En la página 4, la presentación muestra métricas distintas para A, B y C (por ejemplo, cobertura de 83,3 %, 91,7 % y 100 %) y latencias de unos 45, 62 y 118 ms. Ninguna aparece en las salidas del notebook, y la diferencia medida entre C y A es de unos 825 ms, no 56 ms. La respuesta de ejemplo de la página 3 tampoco coincide con la celda 25. La presentación no se versiona en este repositorio, porque sus metadatos incluyen un nombre de usuario.

Verificación posterior (2026-11-22): se comparó el notebook del repositorio de la entrega con la copia local, que tenía el mismo código y las mismas salidas, y se confirmaron los cuatro puntos.

### 5.2 Versión alternativa del 2026-10-24, adoptada en el corte 3

El 2026-10-24 se preparó una versión corregida del corte 2 que no se incluyó en la entrega del 2026-11-02. El corte 3 la adopta por sus resultados medidos.

- Corpus 2.0 y fragmentación por párrafos (sección 3).
- 17 casos: 8 de desarrollo, 4 de reserva y 5 de comportamiento, con unidades de información y criterio de fallo.
- Regla de decisión escrita antes de ver los datos; la reserva se abre una sola vez.
- Validador que rechaza, con un único reintento que informa la causa.
- Revisión humana caso por caso: A la revisó Pablo y la mejora C, Axel.

Resultados: los de la corrida 2 en la sección 4. El notebook de esa versión no tiene salidas guardadas; sus cifras se respaldan con [`evidencias/corte2/`](evidencias/corte2/).

Defectos del notebook de la Clase 11, corregidos en la app:
- `mostrar()` se usaba sin estar definida;
- el estado de `DOC-1001` se citó como `[F1]` cuando venía de la herramienta;
- usaba B y el corpus antiguo en lugar de C y el corpus 2.0;
- los límites del texto no coincidían con los del código;
- la prueba de aislamiento comparaba contra una lista siempre vacía;
- la `fuente` del MCP no coincidía con la bitácora.

### 5.3 Rondas del agente y cambio al flujo predefinido

- **agente_v1.** La corrida inicial (1 de 11) midió fallas de infraestructura. Se corrigió sin tocar las reglas: un cliente de Groq por llamada, control de cupo, reintento de redacción separado de las decisiones. Quedó en 5 de 11 por repeticiones de consulta, falsos positivos del validador, citas sin búsqueda y un rechazo en lugar de aclaración.
- **agente_v2.** Los argumentos vuelven a la observación y hay reglas nuevas contra la repetición y las etiquetas sin procedencia. Dio 7 de 11 y 3 de 6. La compactación de la ronda anterior había quitado la instrucción de escribir cada etiqueta entre corchetes.
- **agente_v3.** Se recuperó esa instrucción, el programa escribe las frases de estado y la traza registra el código HTTP del proveedor. Dio 8 de 11 y 2 de 6: dos 400 del proveedor, estados parafraseados y citas fuera del texto.
- **Cambio.** Las fallas no dependían del prompt, y la ruta se puede decidir con reglas, así que se pasó al flujo predefinido. El agente_v3 queda en la historia de git (commit `3264be1`).
- **Limitación del flujo.** Las reglas se escribieron conociendo los textos de la regresión y de reserva_3, así que reserva_3 no es una prueba ciega del enrutador.

### 5.4 Memoria y cambio a ONNX

La meta era Render Free con 512 MB. Con PyTorch no cupo ninguna configuración. Con ONNX qint8, C con los dos modelos residentes muere al cargar el reordenador; C bajo demanda cabe con un pico de 497 MB y 15 MB de margen, medido bajo emulación. Se aplicaron reducciones de memoria en onnxruntime, en el asignador de memoria y en el arranque del Filesystem MCP. En Render no hubo reinicios por memoria durante las pruebas; Render Free no muestra la memoria, así que la app escribe una línea por turno en el log ([`evidencias/fase0/memoria_y_onnx.md`](evidencias/fase0/memoria_y_onnx.md)).

### 5.5 Otras correcciones del corte 3

| Problema | Corrección | Verificación |
|---|---|---|
| En la corrida 2 de la interfaz, una frase sin etiqueta en la ruta mixta | Contrato rag_v5 por frases | Corrida 3 de la interfaz: 15 de 15 |
| `api_visibility="private"` no cerraba la API | Middleware y validador de sesión por evento | `app/tests/test_api_cerrada.py`; llamada directa con 400 en la URL pública |
| Consultas a Supabase en paralelo fallaban con `RemoteProtocolError` | Consultas en serie con un solo `get_user` | Cambio de conversación: mediana de 1.796 a 614 ms en el servidor |
| Una propuesta de informe sin decidir no reaparecía al recargar | Columna `propuesta_informe` (`app/sql/06_propuesta_informe.sql`) | Paso 9 de la corrida 3 de la interfaz |
| `jsonb` no conserva el orden de las claves | Campos del registro en orden fijo | Prueba de integración de recarga |

### 5.6 Limitaciones y pendientes

- **`normal_01`.** El clasificador pide aclaración en todas las corridas del corte 3, porque la factura no trae NIT ni desglose de impuestos, que el corpus 2.0 exige. No se cambió el prompt ni lo esperado ([`evidencias/fase2/observacion_normal_01.md`](evidencias/fase2/observacion_normal_01.md)).
- **Reserva no ciega.** El resultado oficial de reserva_3 es el 5 de 6 de flujo_v2; el 6 de 6 posterior no es ciego. La prueba ciega son las preguntas de Axel: 5 aprobadas, una de ellas con observación, y 1 fallida (sección 4).
- **`reserva3_registrar_factura`.** Quedó en `ERROR_VALIDACION` con flujo_v2 y flujo_v3; con rag_v5 pasa, pero ese resultado ya no es ciego.
- **Enrutador por reglas.** Una frase con otra forma puede caer en la ruta libre.
- **Paráfrasis de estados.** En algunos casos aprobados del agente_v3, el modelo repitió el estado con otras palabras. El control compara el valor exacto. En el flujo vigente, el modelo no recibe el valor del estado.
- **Latencia y autenticación.** Una respuesta RAG tardó 24 s en Render Free. `get_user` tiene picos de unos 2 s, que no se ocultan porque el token se valida en cada operación.
- **Cupo de Groq.** El límite diario de la cuenta gratuita restringe las pruebas con el modelo.
- **Informes.** No se conservan en el servidor: en Render el disco se borra al reiniciar, por eso se ofrecen para descargar.
- **Material de cortes anteriores.** Los notebooks de las clases 02, 06, 07 y 08 no están en el repositorio; esas clases se respaldan solo con su bitácora.

## 6. Aportes de cada integrante

Tomados de las bitácoras de cada clase y de la evidencia de cada etapa. Donde la bitácora no separa aportes, el equipo confirmó el 2026-11-23 que fue trabajo conjunto.

| Corte y clase | Pablo Garcés Hoyos | Axel Dereck Gutiérrez | Respaldo |
|---|---|---|---|
| Corte 1, Clase 02 | Entorno en Colab con GPU T4, Ollama y `gemma4:e2b`; ejecución de las seis configuraciones | Pregunta normal y ambigua; revisión manual de las seis respuestas; detección de la abstención duplicada; bitácora de la clase | Bitácora C02 (el notebook no está en el repositorio) |
| Corte 1, Clase 03 | Secreto `GROQ_API_KEY`, salidas estructuradas y ejecución de los cinco casos (secciones 2, 7 y 8) | Esquema `AnalisisDocumento`, reglas de decisión y prueba negativa (secciones 3, 8 y 9) | Bitácora C03; [`notebooks/Clase_03_Demo_Groq.ipynb`](notebooks/Clase_03_Demo_Groq.ipynb) |
| Corte 1, Clase 04 y entrega | Corrección de errores, los 11 casos de la matriz y las corridas mock y groq | Esquemas Pydantic del análisis y de los argumentos, refactorización de `ejecutar_pipeline` y ejecución de la suite | Bitácora C04; registro de equipo en las salidas de [`notebooks/Clase_04_Analizador_Documentos_Herramientas.ipynb`](notebooks/Clase_04_Analizador_Documentos_Herramientas.ipynb); [`evidencias/corte1/`](evidencias/corte1/) |
| Corte 2, Clase 06 | Trabajo conjunto: construcción del corpus de prueba D1 a D5, vectorización de los pasajes con `paraphrase-multilingual-MiniLM-L12-v2` y búsqueda por similitud coseno. La bitácora lo registra a nombre de "Estudiante"; el equipo confirmó que fue conjunto. | Trabajo conjunto (ver la columna de Pablo). | Bitácora C06; confirmación del equipo |
| Corte 2, Clase 07 | Trabajo conjunto: pipeline de ingestión, estrategias de fragmentación, metadatos y persistencia del índice. | Trabajo conjunto (ver la columna de Pablo). | Bitácora C07; confirmación del equipo |
| Corte 2, Clase 08 | Trabajo conjunto: integración de Supabase Vector (pgvector), orquestación del RAG con Groq, reglas de citación del prompt y depuración de los errores de validación. | Trabajo conjunto (ver la columna de Pablo). | Bitácora C08; confirmación del equipo |
| Corte 2, Clase 09 | Trabajo conjunto: implementación de BM25, RRF y el reordenador cross-encoder, ajuste de las frases de evidencia del conjunto de prueba, corrección del validador de citas y exportación de las evidencias. | Trabajo conjunto (ver la columna de Pablo). | Bitácora C09; confirmación del equipo |
| Corte 2, entrega del 2026-11-02 (notebook y presentación) | Trabajo conjunto: el notebook de la Clase 09 y la presentación en PDF de 5 páginas entregados el 2026-11-02. | Trabajo conjunto (ver la columna de Pablo). | [`notebooks/Clase_09_Demo_Colab_Mejora_Evaluacion_RAG.ipynb`](notebooks/Clase_09_Demo_Colab_Mejora_Evaluacion_RAG.ipynb); sección 5.1; confirmación del equipo |
| Corte 2, versión del 2026-10-24 (Clase 10) | Integración del corte 1 con RAG, Supabase y Colab, ejecución de las corridas y revisión humana de A | Corpus 2.0, conjunto de 17 casos, clave de Groq de la corrida final y revisión humana de C | Bitácora C10; campo `revisor` en [`revision_humana_corrida_2.json`](evidencias/corte2/corrida_2_rag_v3/revision_humana_corrida_2.json) |
| Corte 2, Clase 10 | Revisión doble independiente de D2, D4, B1 y B4 | La misma, por separado | Bitácora C10 |
| Clase 11 | Trabajo conjunto: configuración de los prompts del agente ReAct, ajuste de `MAX_OPERACIONES` y pruebas de integración. | Trabajo conjunto (ver la columna de Pablo). | Bitácora C11; confirmación del equipo |
| Corte 3, aplicación | Trabajo conjunto: SQL y almacenamiento con RLS, sistema y servidor MCP, interfaz, carga del corpus, despliegue, pruebas y evidencias de las fases 0 a 6. Los commits quedaron en la cuenta de Pablo porque se trabajó en un mismo equipo. | Trabajo conjunto (ver la columna de Pablo). | Historia de git; [`evidencias/`](evidencias/); confirmación del equipo |
| Corte 3, publicación en Render y reinicio para la prueba de recuperación | Trabajo conjunto: publicación del servicio en Render Free con `render.yaml` y reinicio del servicio para comprobar la recuperación de las conversaciones (prueba 2c). | Trabajo conjunto (ver la columna de Pablo). | [`evidencias/fase4/pruebas_url_publica.md`](evidencias/fase4/pruebas_url_publica.md); confirmación del equipo |
| Corte 3, prueba ciega | Ejecución con Playwright en presencia de Axel | Escribió las 6 preguntas y lo esperado antes de usarlas; se ejecutaron con su usuario el 2026-11-23 | [`evidencias/fase4/preguntas_propias_axel.md`](evidencias/fase4/preguntas_propias_axel.md) |

## 7. Uso de asistentes

En los tres cortes se usaron asistentes de programación para:
- adaptar las demostraciones de clase al dominio del proyecto;
- generar y revisar código, pruebas y documentación;
- diagnosticar fallas de las corridas.

Lo producido se verificó así:
- ejecución completa de notebooks y de la aplicación;
- pruebas automáticas;
- corridas reales contra Groq, Supabase y la URL pública;
- revisión humana de cada respuesta evaluada;
- comparación de cada cifra con su archivo de evidencia.

Las cifras que no pudieron respaldarse con un archivo no se usan como resultados (sección 4, rag_v4; sección 5.1, presentación del corte 2).

## 8. Funcionamiento final y conclusiones

### Configuración vigente

| Elemento | Valor |
|---|---|
| Aplicación | https://analizador-documentos-v871.onrender.com |
| Repositorio | https://github.com/pabloGarcesHoyos/analizador-documentos-ia |
| Commit evaluado en la URL pública | `1ce46c5`. Después solo cambiaron documentación, evidencias y un script de prueba del navegador. |
| Flujo y prompts | `flujo_v4`, `rag_v5`, `enrutador_v2` y `analizador_v3` |
| Modelo | `openai/gpt-oss-20b` en Groq, `temperature=0`, `max_completion_tokens` 3000 |
| Recuperación | C bajo demanda: BM25 y embeddings con RRF (c = 60), reordenador sobre 10 candidatos y 3 pasajes, en ONNX qint8 |
| Corpus | 2.0, `analizador_documental_v2-057b729f44ae`, 20 fragmentos |
| Contexto al modelo | Últimos 4 turnos de la conversación |
| Alojamiento | Render Free, Python 3.13.18, `RECUPERACION=C_DEMANDA` |
| Datos | Supabase: Auth, corpus con lectores autorizados, historial e informes con RLS |

### Resultados vigentes

- Regresión del corte 1: 10 de 11; falla `normal_01`.
- reserva_3: 5 de 6, resultado oficial.
- Interfaz: 15 de 15.
- URL pública: 5 de 5.
- Clon limpio: arranca y pasan sus pruebas.
- Prueba ciega con las 6 preguntas de Axel: 5 aprobadas, una con observación, y 1 fallida. La fallida y la observación muestran el límite del enrutador por reglas: una forma de preguntar no prevista cambia la ruta.

### Conclusiones del equipo

- Un JSON válido con citas existentes no garantiza una respuesta fiel. Solo la revisión humana detectó las afirmaciones sin respaldo del corte 2.
- Una evaluación sirve si puede distinguir las opciones. Con 9 fragmentos y 8 casos no podía; con 20 fragmentos, 17 casos y una regla escrita antes, sí.
- Lo que se puede decidir con reglas no debe quedar en manos del modelo: la ruta, la frase de estado y la ubicación de las citas pasaron al programa y los resultados mejoraron.
- Con 512 MB, la recuperación elegida se pudo conservar cambiando el motor de inferencia y midiendo que las métricas no cambiaran.
- El modelo no es determinista. Una corrida aislada no basta para comparar versiones, y los fallos se registran sin ajustar lo esperado.
