# Analizador de Documentos

Aplicación web que responde preguntas sobre políticas de facturación, contratos y documentos de identificación con fuentes citadas, consulta el estado de documentos y solicitudes, clasifica textos de documentos y prepara informes que solo se escriben con aprobación del usuario.

- Repositorio: https://github.com/pabloGarcesHoyos/analizador-documentos-ia
- Aplicación publicada: https://analizador-documentos-v871.onrender.com
- Commit evaluado en la URL pública: `1ce46c5` ([evidencias/fase4/pruebas_url_publica.md](../evidencias/fase4/pruebas_url_publica.md)).

## Problema, usuarios y alcance

Un área administrativa recibe facturas, contratos y documentos de identificación. Las personas que los revisan necesitan saber qué exige cada política, en qué estado va un trámite y si un documento entregado cumple lo mínimo. La aplicación responde con las reglas escritas en el corpus, cita el pasaje que respalda cada frase y consulta el estado en un registro.

Usuarios: personas del área con una cuenta en Supabase Auth autorizada como lectora del corpus.

Qué puede obtener el usuario:

- Respuestas a preguntas de políticas, con fuentes `[F#]` (documento, sección, versión y pasaje).
- El estado de un documento `DOC-XXXX` o de una solicitud `SOL-XXXX`, con la consulta `[T#]` que lo respalda.
- La clasificación de un texto de factura, contrato o documento de identificación, con los campos que faltan.
- Una propuesta de informe en Markdown con la respuesta y sus fuentes, que se escribe solo si el usuario la aprueba.
- Su historial de conversaciones, que se conserva al cerrar sesión, recargar la página y reiniciar el servidor.

Fuera del alcance: el analizador no registra, aprueba, firma, modifica, cancela ni elimina documentos o solicitudes. Esas peticiones se rechazan y se remiten a revisión humana. Tampoco responde temas ajenos al corpus.

Requieren revisión humana: las peticiones de modificar o aprobar algo, los documentos que el clasificador marca con riesgo alto y cualquier respuesta que el usuario quiera convertir en una decisión.

Datos de la demostración: un corpus ficticio de cuatro documentos (`app/corpus/`, versión 2.0-2026-10, con permiso para el repositorio según `app/corpus/manifiesto.json`) y un registro ficticio de cinco expedientes (DOC-1001 a DOC-1003 y SOL-1001 a SOL-1002) dentro de `app/servidor_mcp.py`. No hay datos personales reales.

## Arquitectura y procedencia del código

### Recorrido de una pregunta

1. **Entrada (Gradio, `app.py`).** El usuario escribe en la caja de texto. La interfaz bloquea la entrada y los botones mientras atiende y muestra "Procesando tu consulta…". Si el control de cupo del proveedor espera, muestra "Esperando cupo del proveedor del modelo…".
2. **Sesión.** Antes de cada operación se valida el token del usuario con `auth.get_user` y se renueva si vence en menos de 120 s. El token vive solo en el estado de la sesión de Gradio, en el servidor.
3. **Enrutador por reglas (`sistema.enrutar`).** Decide la ruta sin modelo:
   - `rechazo`: la entrada empieza con una orden prohibida (eliminar, aprobar, firmar, cambiar, registrar, ignorar reglas…).
   - `estado`: hay un código `DOC-XXXX` o `SOL-XXXX` en la entrada, o la entrada se refiere a un código que el mismo usuario escribió antes en esa conversación.
   - `mixta`: hay un código y además una pregunta de políticas.
   - `pide_codigo`: pide seguimiento sin código.
   - `rag`: pregunta con vocabulario del dominio.
   - `documento`: texto que parece un documento entregado.
   - `libre`: nada de lo anterior. Una sola llamada al modelo elige entre aclarar, rechazar o buscar en las políticas.
4. **MCP propio de estado.** En las rutas `estado` y `mixta` se consulta `consultar_estado_solicitud` por stdio, como máximo dos códigos por turno. El programa, no el modelo, escribe la frase del estado con su etiqueta `[T#]`.
5. **RAG.** En `rag`, `mixta` y `libre` con búsqueda, `recuperacion.py` recupera 3 pasajes con recuperación híbrida y reordenamiento (configuración C bajo demanda, ver "Preparación del corpus"). En la ruta mixta solo se busca la parte de la pregunta que no consulta códigos.
6. **Generación y validación (contrato rag_v5).** El modelo `openai/gpt-oss-20b` de Groq devuelve un JSON con esquema estricto: `estado`, una lista de `frases` (cada una con su `texto` y sus `citas`) y `limitacion`. El programa valida cada frase: citas existentes, del turno, sin `[T#]` y sin repetir. Lo que no se sabe va en la limitación. El programa arma el texto con una etiqueta por oración. Si la salida no cumple, se pide un único reintento con todas las reglas; si vuelve a fallar, el turno termina en "Error de validación" y no se muestra texto sin validar. En la ruta mixta se rechaza cualquier frase que afirme el estado de un código.
7. **Clasificador del corte 1.** En la ruta `documento` se usa el prompt `analizador_v3` y su esquema, con las reglas de decisión del corte 1 (`validar_y_decidir_clasificacion`).
8. **Informe con aprobación.** Si el usuario pide un informe y la respuesta tiene fuentes `[F#]`, se arma una propuesta con contenido, destino `informe_<12 hex>.md` y huella SHA-256. La interfaz muestra el contenido completo y los botones Aprobar y Rechazar. Ver "Configuración del MCP".
9. **Guardado.** `almacenamiento.guardar_turno` guarda la pregunta y la respuesta con estado, fuentes, herramientas, limitación, detalle del error, propuesta de informe y traza. La traza registra ruta, llamadas, tokens, reintentos y salidas rechazadas, con secretos filtrados.
10. **Respuesta.** La interfaz muestra un rótulo según el estado y la ruta (por ejemplo "Respondida con datos del registro" o "Sin evidencia"), la respuesta, la limitación, y bloques desplegables con las fuentes y las consultas. Un error técnico nunca se presenta como falta de información.

### Archivos de `app/`

| Archivo | Responsabilidad | Procedencia |
|---|---|---|
| `app.py` | Interfaz Gradio: inicio y cierre de sesión, lista de conversaciones con "Ver más", chat con fuentes y consultas, aprobación del informe, bloqueo durante la atención, validador de sesión por evento, bloqueo de la API directa y arranque en `GRADIO_SERVER_NAME` y `PORT`. | Clase 11, puntos 7 y 8 (entrada y controles), reemplazando las celdas por eventos de Gradio. |
| `sistema.py` | Enrutador, rutas, contratos rag_v5 y del clasificador, validación de frases y citas, cliente de Groq con control de cupo, clientes MCP, armado y escritura aprobada del informe, línea de memoria por turno. | Clase 11, puntos 4, 4.b, 5 y 6 (`consultar_por_mcp`, `guardar_informe_por_mcp`, `validar_decision`, `controlar_operacion`); corte 2, secciones 1, 9 y 10 (`ControlTasa`, `validar_respuesta_rag`, `enrutar`); corte 1 (`AnalisisDocumento`, `validar_y_decidir_clasificacion`). |
| `almacenamiento.py` | Autenticación por sesión, conversaciones, mensajes, decisiones de informe. Comprueba el propietario en cada operación con un cliente nuevo por operación. | Nuevo: reemplaza `MEMORIA` y `guardar_turno` de la Clase 11 por Supabase con RLS. |
| `recuperacion.py` | Tokenizador XLM-R, embeddings y reranker ONNX, BM25, fusión RRF y modos C bajo demanda y B. | Corte 2, sección 7 (`tokenizar_bm25`, `recuperar_semantica`, `buscar_bm25`, `fusionar_rrf`, `reordenar`) y Clase 11, punto 3. |
| `servidor_mcp.py` | Servidor MCP propio, de solo lectura, con la herramienta `consultar_estado_solicitud`. | Clase 11, punto 4 (`consultar_estado_solicitud`, `Registro`, `ResultadoEstado`) y registro del corte 2. |
| `cargar_corpus.py` | Carga única e idempotente del corpus en Supabase con el usuario que la ejecuta como dueño. | Corte 2, secciones 3, 4 y 6 (`limpiar`, `secciones`, `fragmentar`, `filas_en_supabase`, `rpc_semantica`). |
| `descargar_modelos.py` | Descarga los modelos ONNX y el tokenizador en revisiones fijas y verifica su huella. | Nuevo. |
| `sql/` | Esquema, RLS y funciones, en orden de ejecución. | Corte 2 (tabla y búsqueda del corpus) y nuevo (historial e informes). |
| `corpus/` | Corpus ficticio 2.0 y su manifiesto. | Corte 2. |
| `mcp_archivos/` | `package.json` y `package-lock.json` del Filesystem MCP. | Clase 11, punto 4.b. |
| `tests/` | Pruebas unitarias, de integración, de regresión y de navegador. | Nuevo; la regresión usa los casos del corte 1. |
| `requirements.txt` | Dependencias con versiones fijas. | |
| `.env.ejemplo`, `.env.pruebas.ejemplo` | Plantillas de variables, sin valores secretos. | |

Los notebooks de origen están en [`notebooks/`](../notebooks/).

### Qué se guarda y qué va al modelo

- Se guardan todos los mensajes de cada conversación, de usuario y de asistente, en el orden en que ocurrieron. Una conversación nueva no borra las anteriores.
- Al modelo se le envía una ventana de los últimos 4 turnos (8 mensajes) de esa conversación, solo con rol y contenido (`TURNOS_CONTEXTO = 4` en `sistema.py` y `almacenamiento.py`). La ventana se lee de Supabase en cada turno.
- La ruta `estado` no envía nada al modelo. El valor de un estado nunca se envía al modelo en la ruta mixta.

## Requisitos

- Python 3.13. Probado con 3.13.15 en macOS 26.5 (Apple Silicon) y con 3.13.18 en Linux, en Render. No se probó con Windows ni con Python 3.14.
- Dependencias de `app/requirements.txt`: gradio 6.31.0, supabase 2.32.0, groq 1.7.0, pydantic 2.13.5, mcp 2.3.0, onnxruntime 1.31.1, sentencepiece 0.2.2, numpy 2.5.5, rank-bm25 0.2.2, python-dotenv 1.2.4 y nodejs-wheel 24.19.0.
- Pruebas: `requirements-pruebas.txt` (pytest 9.2.0, pytest-asyncio 1.4.1.post1 y psycopg 3.3.8). Prueba de navegador: `requirements-e2e.txt` (playwright 1.64.1).
- Cuentas: un proyecto de Supabase (gratuito sirve) y una clave de Groq.
- Node con npm para el Filesystem MCP. Si no hay Node en el sistema, `nodejs-wheel` instala `node` y `npm` dentro del entorno virtual.
- Modelos: 242 MB de descarga inicial (embeddings 123,5 MB y reranker 118,6 MB, en ONNX qint8). En ejecución, la configuración C bajo demanda reposa en unos 362 MB y llega a unos 497 MB durante una consulta (medición emulada, ver "Preparación del corpus").

## Instalación desde un clon limpio

PowerShell (no probado por el equipo), desde una carpeta donde podamos clonar:

```powershell
git clone https://github.com/pabloGarcesHoyos/analizador-documentos-ia
cd analizador-documentos-ia
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r app/requirements.txt
Copy-Item app/.env.ejemplo app/.env
cd app
..\.venv\Scripts\python.exe descargar_modelos.py
..\.venv\Scripts\npm.cmd ci --prefix mcp_archivos --omit=dev
```

Linux/macOS (probado en macOS):

```bash
git clone https://github.com/pabloGarcesHoyos/analizador-documentos-ia
cd analizador-documentos-ia
python3.13 -m venv .venv
.venv/bin/python -m pip install -r app/requirements.txt
cp app/.env.ejemplo app/.env
cd app
../.venv/bin/python descargar_modelos.py
../.venv/bin/npm ci --prefix mcp_archivos --omit=dev
cd ..
```

Si el Python 3.13 de tu equipo tiene otro nombre (por ejemplo `python3` o `py -3.13` en Windows), úsalo en lugar de `python3.13`; compruébalo antes con `--version`.

`descargar_modelos.py` imprime `modelos verificados` cuando todos los archivos tienen la huella esperada. `npm ci` instala el Filesystem MCP con la versión del lock.

Antes de ejecutar, completa `app/.env` (sección siguiente) y prepara Supabase (secciones "Preparación del corpus" y "Usuarios e historiales").

## Variables y secretos

`app.py` carga `app/.env` desde su propia carpeta, sin importar el directorio actual. Una variable definida en el entorno del proceso tiene prioridad sobre el archivo. En Render las variables se configuran en el panel. `.env` y `.env.pruebas` no se versionan; solo `.env.ejemplo` y `.env.pruebas.ejemplo`, sin valores secretos.

| Variable | Uso | ¿Obligatoria? |
|---|---|---|
| `GROQ_API_KEY` | Clave de Groq. | Sí. |
| `GROQ_MODEL` | Modelo generativo. Por defecto `openai/gpt-oss-20b`. | No. |
| `GROQ_TPM` | Tokens por minuto de la cuenta de Groq, para el control de cupo. Por defecto 8000. | No. |
| `GROQ_RPM` | Solicitudes por minuto de la cuenta de Groq. Por defecto 30. | No. |
| `SUPABASE_URL` | Project URL de Supabase, con corpus e historiales. | Sí. |
| `SUPABASE_PUBLISHABLE_KEY` | Clave publicable (`sb_publishable_…`). Configura el acceso a la Data API; no identifica a un usuario. La app rechaza cualquier clave que no sea publicable. | Sí. |
| `CORPUS_ID` | Identificador del corpus que imprime `cargar_corpus.py`. | Sí. |
| `CORPUS_PROPIETARIO_ID` | UUID del usuario dueño del corpus que imprime `cargar_corpus.py`. | Sí. |
| `RECUPERACION` | `C_DEMANDA` (por defecto) o `B`. | No. |
| `GRADIO_SERVER_NAME` | `127.0.0.1` en local (por defecto) y `0.0.0.0` en el alojamiento. | No. |
| `PORT` | Puerto HTTP. Por defecto 7860; en Render lo asigna el servicio. | No. |
| `MALLOC_ARENA_MAX` | Recomendado `2` para bajar la memoria en Linux. | No. |
| `OMP_NUM_THREADS` | Recomendado `1`. | No. |
| `MCP_FALLO_FORZADO` | Solo para pruebas: con `1`, el servidor de estado falla a propósito para comprobar el error técnico. En producción no se define. | No. |

Si falta una variable obligatoria, la app no arranca y dice cuál falta, sin mostrar valores. No hay lista de contraseñas en `.env`: cada persona inicia sesión con su cuenta. Las pruebas de integración usan `app/.env.pruebas` con `PRUEBA_A_EMAIL`, `PRUEBA_A_PASSWORD`, `PRUEBA_B_EMAIL`, `PRUEBA_B_PASSWORD`, `PRUEBA_DEMO_EMAIL` y `PRUEBA_DEMO_PASSWORD`.

## Preparación del corpus y de los datos

### Corpus

Cuatro documentos ficticios en `app/corpus/`: `politicas_facturacion.md`, `gestion_contratos.md`, `documentos_identificacion.md` y `seguimiento_y_seguridad.md`, versión 2.0-2026-10.

Fragmentación por párrafos dentro de cada sección, con el encabezado "Título / Sección" en cada fragmento. El tope es de 120 tokens; si un párrafo lo supera, se divide en ventanas con solapamiento de 20. El corpus 2.0 produce 20 fragmentos y ninguno necesita ventanas.

### Embeddings y reordenamiento

- Embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revisión `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, 384 dimensiones, mean pooling y vector normalizado, similitud coseno.
- Reordenamiento: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, revisión `1427fd652930e4ba29e8149678df786c240d8825`, con un máximo de 256 tokens por par.
- Ambos se ejecutan con ONNX Runtime con las exportaciones oficiales qint8 de cada repositorio, sin PyTorch. La app descarga `onnx/model_qint8_arm64.onnx`, pero no es un modelo exclusivo de ARM: cada repositorio publica el mismo archivo qint8 con tres nombres (`model_qint8_arm64.onnx`, `model_qint8_avx512.onnx` y `model_qint8_avx512_vnni.onnx`). Los tres tienen la misma huella SHA-256 y el mismo tamaño en la revisión fijada (API de archivos de Hugging Face), y `descargar_modelos.py` verifica esa huella al descargar:

  | Modelo | Huella SHA-256 de los tres nombres | Tamaño |
  |---|---|---|
  | Embeddings | `783fea82d71a58179b830a4dbd2d58447e640609e98eedf9ffa12622d375a672` | 118.412.398 bytes |
  | Reordenamiento | `1825907d6c1a9001ff78124780bbde20a614a8c3df3b63409cf3c72c6fe5c8b4` | 118.620.017 bytes |

  Por eso en Render, que es x86, corre el mismo archivo que en local. ONNX Runtime elige los kernels int8 según la CPU, así que los puntajes pueden variar un poco entre máquinas. Con la configuración final se obtienen las mismas métricas agregadas del corte 2. En 42 de 51 selecciones el orden es idéntico; en las 9 restantes cambia la posición. El coseno mínimo frente a PyTorch es 0,967.

### Recuperación elegida

Configuración C del corte 2: búsqueda semántica (10 candidatos en Supabase con `analizador_buscar_fragmentos_autorizado`) y BM25 (10 candidatos; k1 1,5, b 0,75, épsilon 0,25), fusión RRF (constante 60) y reordenamiento con el cross-encoder. Pasan 3 pasajes al modelo.

Justificación (corte 2, [`evidencias/corte2/corrida_2_rag_v3/evaluacion/decision.json`](../evidencias/corte2/corrida_2_rag_v3/evaluacion/decision.json), regla cobertura > MRR > Recall@3 > simplicidad, casos de desarrollo):

| Configuración | Cobertura | MRR | Recall@3 | Latencia mediana |
|---|---|---|---|---|
| A semántica | 0,875 | 0,875 | 0,875 | 136 ms |
| B híbrida RRF | 0,812 | 0,792 | 0,812 | 137 ms |
| C híbrida con reordenamiento | 0,938 | 0,938 | 0,938 | 865 ms |

Memoria en un contenedor de 512 MB, emulado en local:

| Modo | ¿Sobrevive? | Pico | En reposo | Recuperación por consulta |
|---|---|---|---|---|
| C con ambos modelos cargados | No: muere al cargar el reranker | más de 512 MB | | |
| C bajo demanda (`C_DEMANDA`) | Sí | 497 MB | 362 MB | 1,8 a 2,2 s |
| B (embeddings cargados, BM25 y RRF, sin reordenamiento) | Sí | 460 MB | 446 MB | 28 a 62 ms |

`C_DEMANDA` carga cada modelo solo durante la consulta y lo libera al terminar. Así conserva la recuperación del corte 2 dentro de 512 MB. En Render Free corre sin reinicios por memoria hasta ahora (Events del servicio). Render Free no muestra la memoria, así que la app escribe en los logs, después de cada turno, una línea `turno ruta=… ms=… rss_mb=… pico_mb=… hijos_mb=… pico_hijos_mb=…`. Si el servicio muere por memoria, se cambia `RECUPERACION` a `B`.

### Pasos que se hacen una vez

1. En el SQL Editor de Supabase, ejecutar en orden `sql/01_corpus.sql`, `sql/02_historial.sql`, `sql/03_informes.sql`, `sql/05_presentacion.sql` y `sql/06_propuesta_informe.sql`. Todos son idempotentes. `sql/04_comprobaciones.sql` es opcional y solo consulta que RLS y las políticas estén activas.
2. Crear en Supabase Auth el usuario dueño del corpus (sección siguiente).
3. Cargar el corpus con ese usuario:
   ```bash
   cd app
   ../.venv/bin/python cargar_corpus.py
   ```
   Pide la contraseña sin mostrarla; el correo se toma de `CARGA_EMAIL` o se pregunta. Fragmenta, calcula los embeddings, sube las filas con `upsert` y verifica que el número de filas coincida y que la búsqueda remota devuelva el mismo primer resultado que la exacta local. Si el corpus ya está completo, no lo reescribe (`--forzar` lo sube otra vez). Al terminar imprime `CORPUS_ID`, `CORPUS_PROPIETARIO_ID` y el SQL para autorizar lectores. Con el corpus 2.0 el identificador es `analizador_documental_v2-057b729f44ae`, el mismo del corte 2.

Al atender una pregunta no se inserta nada en el corpus: solo se lee.

### Quién puede leer el corpus

La tabla `analizador_fragmentos` tiene RLS. Su dueño la lee y la escribe. Otro usuario solo la lee si está en `lectores_corpus` para ese dueño y ese corpus. Un usuario autenticado que no está autorizado recibe "Sin acceso", distinto de "Sin evidencia". Estos permisos no dan acceso al historial de nadie.

## Usuarios e historiales

### Crear usuarios de prueba

1. En Supabase, Authentication, Users, **Add user**, **Create new user**, con correo y contraseña, marcando **Auto Confirm User**.
2. Autorizarlo como lector del corpus en el SQL Editor (el valor del correo lo escribe quien administra el proyecto):
   ```sql
   insert into public.lectores_corpus (propietario_id, corpus_id, lector_id)
   select 'CORPUS_PROPIETARIO_ID'::uuid, 'CORPUS_ID', id from auth.users where email = 'CORREO_DEL_LECTOR'
   on conflict do nothing;
   ```
3. Para las pruebas de integración se usan tres usuarios (A, B y demostración); sus credenciales van solo en `app/.env.pruebas`.

### Tablas y políticas

| Tabla | Contenido | Políticas |
|---|---|---|
| `conversaciones` | `id`, `usuario_id` (dueño), `titulo`, `creada_en` | Cada usuario lee e inserta solo las suyas. |
| `mensajes` | `id` creciente (orden), `conversacion_id`, `usuario_id`, `rol`, `contenido`, `estado`, `fuentes`, `herramientas`, `limitacion`, `detalle_error`, `propuesta_informe`, `traza`, `creado_en` | Se lee o inserta un mensaje solo si es del usuario y su conversación también. La llave foránea `(conversacion_id, usuario_id)` impide colgar un mensaje de una conversación ajena. |
| `acciones_informe` | Decisión aprobada o rechazada, resultado ejecutada o fallida, destino y huella | Una decisión por mensaje (llave única); solo el dueño la lee; el resultado se escribe una sola vez. |

No hay políticas de borrado ni de edición del historial. Conocer el UUID de una conversación ajena no da acceso: la prueba en la URL pública lo confirma.

### Sesión y recuperación del historial

- Cada sesión de Gradio guarda solo `access_token`, `refresh_token`, `expira_en`, `usuario_id` y `correo`. No hay cliente global: cada operación crea un cliente con el token del usuario y valida su identidad con `auth.get_user`.
- La contraseña se usa una vez para iniciar sesión y la caja se vacía.
- Al recargar la página, la sesión de Gradio se pierde y hay que volver a iniciar sesión. Al entrar, la lista de conversaciones y sus mensajes se leen de Supabase.
- Al reiniciar el servidor no se pierde nada: el historial vive en Supabase. Se comprobó reiniciando el servicio en Render.
- Al recargar, una conversación se ve igual que en vivo: estado, limitación, fuentes, consultas y decisiones del informe. Si una propuesta de informe quedó sin decidir, vuelven a aparecer Aprobar y Rechazar.
- Cerrar sesión revoca la sesión en Supabase y limpia el estado.

## Configuración del MCP

### MCP propio de estado (`servidor_mcp.py`)

- Procedencia: propio, a partir de la Clase 11. SDK `mcp` 2.3.0 (`MCPServer`).
- Transporte: stdio. `sistema.ClienteMCPEstado` lo inicia como subproceso en cada consulta, con un límite de 15 s. No hay que arrancarlo aparte.
- Herramienta habilitada: `consultar_estado_solicitud(codigo_solicitud)`, de solo lectura. El código debe cumplir `^(?:DOC|SOL)-[0-9]{4}$`. Devuelve `codigo_solicitud`, `encontrado`, `registro`, `fuente` y `origen`.
- Uso: rutas `estado` y `mixta`, como máximo dos códigos por turno.
- Errores: si el servidor falla o no responde, el turno termina en "Error técnico", distinto de "no existe en el registro". Para probarlo, la variable `MCP_FALLO_FORZADO=1` fuerza la falla.

### Filesystem MCP (informe)

- Procedencia: `@modelcontextprotocol/server-filesystem` 2.2.0, instalado con `npm ci` desde `mcp_archivos/package-lock.json`. Se ejecuta con el `node` del sistema o el de `nodejs-wheel`.
- Transporte: stdio, con una sola carpeta permitida: `app/informes/`.
- Operación usada: escribir un archivo. No se usa ninguna otra operación del servidor.
- Aprobación humana:
  - la interfaz muestra el contenido completo y el destino;
  - el usuario aprueba o rechaza con un botón, y la decisión queda registrada en `acciones_informe`;
  - `escribir_informe_aprobado` comprueba en el código que la decisión sea "aprobada", que no tenga resultado, que la huella SHA-256 coincida con el contenido aprobado y que el destino tenga el formato `informe_<12 hex>.md`;
  - después de escribir, se verifica la huella del archivo y se ofrece la descarga desde una copia temporal.
- Duplicados: la llave única impide registrar dos decisiones para el mismo mensaje, un conjunto en memoria impide dos escrituras simultáneas, y el resultado solo se registra una vez. Un doble clic deja un solo archivo; está probado en el navegador.
- Errores: si la escritura falla, queda registrada como "fallida" y no se reintenta.
- Almacenamiento: los informes se escriben en el disco del servidor, que en Render se borra al reiniciar. Por eso se ofrecen para descargar en el momento.

## Ejecución local

Desde la raíz clonada, con `app/.env` completo y Supabase preparado:

```bash
cd app
../.venv/bin/python app.py
```

En PowerShell: `cd app` y `..\.venv\Scripts\python.exe app.py`.

La app queda en http://127.0.0.1:7860 (o en el `PORT` configurado). Se detiene con Ctrl+C. Los dos servidores MCP los inicia la app cuando los necesita.

## Despliegue de referencia en Render

El repositorio incluye `render.yaml` (Blueprint):

1. En Render, **New**, **Blueprint**, y seleccionar este repositorio, rama `main`, archivo `render.yaml`.
2. El servicio web queda con **Root Directory: `app`**, plan Free y estos comandos:
   - Build Command: `pip install -r requirements.txt && python descargar_modelos.py && npm ci --prefix mcp_archivos --omit=dev`
   - Start Command: `python app.py`
3. Variables fijas en `render.yaml`: `PYTHON_VERSION=3.13.18`, `GRADIO_SERVER_NAME=0.0.0.0`, `GROQ_MODEL`, `GROQ_TPM=8000`, `GROQ_RPM=30`, `RECUPERACION=C_DEMANDA`, `MALLOC_ARENA_MAX=2` y `OMP_NUM_THREADS=1`. `PORT` lo asigna Render.
4. Secretos que se escriben en el panel: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `GROQ_API_KEY`, `CORPUS_ID` y `CORPUS_PROPIETARIO_ID`.
5. Auth, corpus, lectores, historial e informes usan el mismo proyecto de Supabase; nada del historial depende del disco del servidor.
6. URL publicada: https://analizador-documentos-v871.onrender.com. Commit evaluado: `1ce46c5`, con las pruebas de [`evidencias/fase4/pruebas_url_publica.md`](../evidencias/fase4/pruebas_url_publica.md).

Render Free apaga el servicio tras 15 minutos sin uso y la primera visita después tarda en arrancar. El Node que incluye Render ejecuta el Filesystem MCP.

## Pruebas y resultados observados

Comandos, desde la raíz:

```bash
.venv/bin/python -m pip install -r requirements-pruebas.txt
.venv/bin/python -m pytest
.venv/bin/python -m pytest -m "integracion and not groq"
.venv/bin/python -m pytest -m "groq and not reserva and not reserva2 and not reserva3" app/tests/test_regresion_corte1.py
```

- La primera corre las pruebas que no usan servicios externos (548 el 2026-11-22; el número crece con los archivos versionados que revisa `test_estilo.py`).
- La segunda corre 17 pruebas contra Supabase real y necesita `app/.env.pruebas`.
- La tercera es la regresión del corte 1 con Groq.
- Las pruebas de navegador están en `app/tests/e2e/` y necesitan `requirements-e2e.txt` y `python -m playwright install chromium`.

| Caso | Entrada | Ruta esperada | Resultado observado | Evidencia | Estado |
|---|---|---|---|---|---|
| RAG con fuentes | "¿Qué requisitos tiene una factura y en qué estado está DOC-1001?" | mixta | Frase del registro `[T1]` y requisitos con `[F1]` y `[F2]` | [fase4](../evidencias/fase4/pruebas_url_publica.md), [fase3](../evidencias/fase3/prueba_interfaz.md) | Aprobado |
| Falta de evidencia | "¿Cuál es el plazo para pagar una factura después de contabilizarla?" | rag | "Sin evidencia", sin inventar un plazo | [fase4](../evidencias/fase4/pruebas_url_publica.md) | Aprobado |
| Entrada incompleta | "¿Cómo va la revisión de mi documento?" | pide_codigo | Pide el código, sin consultar | [fase3](../evidencias/fase3/prueba_interfaz.md) | Aprobado |
| Herramienta autorizada | "¿En qué estado está DOC-1001?" | estado | Frase del registro con `[T1]`, sin llamar al modelo | [fase3](../evidencias/fase3/prueba_interfaz.md) | Aprobado |
| Acción prohibida | "Elimina el documento DOC-1001" | rechazo | Rechazo y remisión a revisión humana | [fase3](../evidencias/fase3/prueba_interfaz.md) | Aprobado |
| Error técnico | Pregunta de políticas con una clave de Groq inválida, probada en local (no en la URL pública) | rag | "Error técnico… No significa que falte información" | [fase4](../evidencias/fase4/pruebas_url_publica.md) | Aprobado |
| Informe con aprobación | "¿Qué datos debe traer una factura? Haz un informe" | rag | Doble clic en Aprobar deja un solo archivo, igual al mostrado; rechazar no escribe. En la URL pública, el Filesystem MCP de Render escribió el informe aprobado y el archivo descargado tiene la misma huella que lo mostrado | [fase3](../evidencias/fase3/prueba_interfaz.md), [fase4](../evidencias/fase4/pruebas_url_publica.md) | Aprobado |
| Dos usuarios | A y B al mismo tiempo | | B no ve ninguna conversación de A, ni por la lista ni por el UUID | [fase4](../evidencias/fase4/pruebas_url_publica.md) | Aprobado |
| Dos conversaciones de una persona | Cambio entre conversaciones del demo | | Cada una muestra su contenido | [fase3](../evidencias/fase3/prueba_interfaz.md) | Aprobado |
| Historial tras cerrar sesión y reiniciar | Reinicio del servicio en Render | | Las dos conversaciones se ven idénticas | [fase4](../evidencias/fase4/pruebas_url_publica.md) | Aprobado |
| Lectura o inserción en una conversación ajena | UUID de A usado por B | | Lectura y escritura negadas por RLS | [fase1](../evidencias/fase1/pruebas_integracion.md) | Aprobado |
| Regresión del corte 1 | 11 casos | | 10 de 11; falla `normal_01` | [fase2](../evidencias/fase2/regresion_corte1_20261122T2027_flujo_v4.md) | 10 aprobados, 1 fallido |
| Reserva 3 | 6 casos | | 5 de 6 (resultado oficial, flujo_v2); 6 de 6 con rag_v5, ya no ciega | [flujo_v2](../evidencias/fase2/reserva3_flujo_20261122T1901_flujo_v2.md), [rag_v5](../evidencias/fase2/reserva3_flujo_20261122T2030_flujo_v4.md) | Ver limitaciones |
| Preguntas propias no vistas | 6 preguntas que escribió Axel, ejecutadas en la URL pública con su usuario | | 5 aprobadas; la 1 tomó la ruta mixta en vez de estado; la 5 se aprobó con la observación de que rechazó por la ruta libre, con un texto genérico | [fase4](../evidencias/fase4/preguntas_propias_axel.md) | 5 aprobadas (1 con observación), 1 fallida |

Las métricas de recuperación del corte 2 están en [`evidencias/corte2/`](../evidencias/corte2/).

## Seguridad, problemas frecuentes y limitaciones

### Seguridad

- No se usa `service_role` ni ninguna clave administrativa: solo la clave publicable y la sesión de cada usuario. `test_sql.py` y `test_cargar_corpus.py` verifican que el SQL y el cargador no la usen, y la configuración rechaza cualquier clave que no sea publicable.
- RLS en todas las tablas; los historiales son privados y el corpus solo lo leen los lectores autorizados.
- Los secretos viven solo en `app/.env`, `app/.env.pruebas` y el panel de Render. Las trazas, los logs y las evidencias filtran tokens, claves y correos.
- La API de Gradio está cerrada:
  - `/gradio_api/info`, `/call`, `/run`, `/api`, `/upload` y `/openapi.json` responden 404;
  - todos los eventos, salvo el inicio de sesión, exigen una sesión válida antes de entrar a la cola, y sin ella responden 400 sin datos.
- Si una clave llega al repositorio o a un chat, se rota en el proveedor. Así se hizo con las contraseñas de prueba.

### Problemas frecuentes

| Síntoma | Qué revisar |
|---|---|
| "La aplicación no arranca: Faltan variables de entorno: …" | Completar en `app/.env` (o en el panel) la variable indicada. |
| "No se pudo iniciar sesión: revisa el correo y la contraseña." | Que el usuario exista y esté confirmado en Supabase Auth. |
| "La sesión venció…" | Volver a iniciar sesión; el refresh token caducó o fue revocado. |
| "La conversación no existe o no pertenece a tu usuario." | Es el control de propietario; no se resuelve desactivando RLS. |
| "Sin acceso: tu usuario no está autorizado…" | Agregar el usuario a `lectores_corpus`. |
| Respuestas sin evidencia en preguntas que el corpus sí cubre | Que `CORPUS_ID` y `CORPUS_PROPIETARIO_ID` correspondan al corpus cargado y que la carga haya terminado con el número de filas correcto. |
| El servicio se reinicia o muere | Buscar el reinicio por memoria en Events de Render y la línea `turno … pico_mb=…` en los logs; cambiar `RECUPERACION` a `B`. |
| "Error técnico" con detalle del servidor de estado | Que `servidor_mcp.py` arranque con el mismo Python. |
| No se escribe el informe | Que `npm ci --prefix mcp_archivos` se haya ejecutado y exista `node`. |
| Error de conexión con Supabase | El plan gratuito pausa el proyecto tras una semana sin actividad; reanudarlo en el panel. |
| La primera visita tarda | Render Free arranca el servicio dormido. |
| "Esperando cupo del proveedor del modelo…" o error 429 | Límite por minuto de Groq; esperar. Con el límite diario de la cuenta gratuita (200.000 tokens) agotado, las preguntas que usan el modelo fallan hasta el día siguiente. |

### Limitaciones

- `normal_01` (regresión del corte 1): el clasificador pide aclaración en todas las corridas registradas, porque la factura no trae NIT ni desglose de impuestos, que el corpus 2.0 exige. Se documenta sin cambiar el prompt ni lo esperado.
- La reserva 3 no es una prueba ciega del enrutador: sus textos se conocían al escribir las reglas y al diseñar rag_v5. Su resultado oficial es el 5 de 6 de flujo_v2. La prueba ciega son las preguntas propias de Axel: 5 aprobadas, una con observación, y 1 fallida.
- El enrutador es por reglas: una frase con otra forma puede tomar otra ruta. En la prueba ciega, "¿Me puedes decir cómo va el trámite SOL-2048?" fue a la ruta mixta porque "puedes" cuenta como señal de pregunta de políticas, y "Quiero que apruebes..." se rechazó por la ruta libre, con una llamada al modelo, porque no empieza con la orden, y con una respuesta genérica ("no puedo ayudar con esa solicitud").
- Latencia en Render Free: en las pruebas de la URL pública, una respuesta RAG tardó 24 s. En local, en la corrida 3 de la prueba en el navegador, las respuestas tardaron entre 2,9 y 8,0 s ([evidencias/fase3/prueba_interfaz.md](../evidencias/fase3/prueba_interfaz.md)). La primera visita tras dormir tarda más.
- `get_user` en Supabase Auth tiene picos de hasta unos 2 s, así que algunos cambios de conversación pasan de 2 s. Validar el token en cada operación es una regla del proyecto.
- El límite diario de Groq en la cuenta gratuita restringe cuántas pruebas con el modelo caben en un día.
- Los informes no se conservan en el servidor.
- Los modelos ONNX qint8 dan puntajes algo distintos a PyTorch (9 de 51 selecciones con otra posición).

## Presentación y evidencias

- Presentación: [`presentacion_proyecto.pdf`](presentacion_proyecto.pdf), 15 diapositivas. La fuente está en [`presentacion/presentacion_proyecto.html`](../presentacion/presentacion_proyecto.html) y el PDF se regenera con `.venv/bin/python presentacion/exportar_pdf.py` desde la raíz, con las dependencias de `requirements-e2e.txt` y Chromium de Playwright.
- Evidencias por fase: [`evidencias/`](../evidencias/).
- Notebooks de los cortes anteriores: [`notebooks/`](../notebooks/).

## Bitácora unificada del proyecto

[`BITACORA_PROYECTO.md`](../BITACORA_PROYECTO.md): problema y alcance de los tres cortes, decisiones técnicas con su alternativa descartada, experimentos y pruebas con su evidencia, errores, limitaciones, aportes del equipo y configuración vigente.

## Equipo y referencias

- Pablo Garcés Hoyos y Axel Dereck Gutiérrez. Curso Inteligencia Artificial Generativa y Sistemas Inteligentes, EAM 2026-II, profesor Robert Garcia Rey. Las responsabilidades de cada integrante se detallan en la bitácora.
- Datos: corpus y registro ficticios creados por el equipo para el curso.
- Licencia del código: MIT ([`LICENSE`](../LICENSE)). Modelos: los de cada repositorio en Hugging Face (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` y `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`). Filesystem MCP: el de su paquete en npm.
- Referencias: documentación de Gradio 6, Supabase (Auth, RLS y pgvector), Groq (salidas estructuradas y límites), Model Context Protocol (SDK de Python y servidor de archivos), ONNX Runtime y Render (Blueprints, versión de Python y runtimes nativos).
