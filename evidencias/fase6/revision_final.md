# Fase 6: revisión final del repositorio publicado

Fecha: 2026-11-22 (hora de Colombia; 2026-11-23 en UTC). Repositorio: https://github.com/pabloGarcesHoyos/analizador-documentos-ia, rama `main`. Fuentes de los requisitos: la guía de entrega final de la Clase 12 y su plantilla del README.

Estados: **cumple**, **parcial** (cumple con una salvedad que se indica) o **pendiente**.

## 1. Requisitos de la guía de la Clase 12

| # | Requisito | Dónde se cumple | Evidencia | Estado |
|---|---|---|---|---|
| 1 | Aplicación Gradio que recibe una solicitud nueva y muestra el resultado sin ejecutar celdas | [`app/app.py`](../../app/app.py) | [`fase3/prueba_interfaz.md`](../fase3/prueba_interfaz.md), [`fase4/pruebas_url_publica.md`](../fase4/pruebas_url_publica.md) | cumple |
| 2 | Estructura: `README.md`, `.gitignore`, `BITACORA_PROYECTO.md`, `notebooks/`, `evidencias/`, `app/` con sus archivos | Raíz del repositorio y [`app/`](../../app/) | Listado de archivos versionados | cumple |
| 3 | `app.py` presenta la interfaz y no duplica la lógica | [`app/app.py`](../../app/app.py) | [`app/tests/test_app.py`](../../app/tests/test_app.py) | cumple |
| 4 | `sistema.py` coordina recuperación, contratos, validación, flujo y clientes MCP, y recibe la identidad autorizada | [`app/sistema.py`](../../app/sistema.py) | [`app/tests/test_sistema.py`](../../app/tests/test_sistema.py) | cumple |
| 5 | `almacenamiento.py` guarda y recupera conversaciones y comprueba el propietario antes de leer o escribir | [`app/almacenamiento.py`](../../app/almacenamiento.py) | [`fase1/pruebas_integracion.md`](../fase1/pruebas_integracion.md) | cumple |
| 6 | `servidor_mcp.py` solo si el MCP es propio | [`app/servidor_mcp.py`](../../app/servidor_mcp.py) | [`app/tests/test_servidor_mcp.py`](../../app/tests/test_servidor_mcp.py) | cumple |
| 7 | Extracción desde los notebooks, conservando la mejora justificada en la Clase 09 | Tabla de procedencia en [`app/README.md`](../../app/README.md); recuperación C en [`app/recuperacion.py`](../../app/recuperacion.py) | [`fase0/memoria_y_onnx.md`](../fase0/memoria_y_onnx.md), [`app/tests/test_recuperacion.py`](../../app/tests/test_recuperacion.py) | cumple |
| 8 | Carga del corpus fuera de la atención de preguntas | [`app/cargar_corpus.py`](../../app/cargar_corpus.py) | [`app/tests/test_cargar_corpus.py`](../../app/tests/test_cargar_corpus.py) | cumple |
| 9 | Identidad de Supabase Auth, RLS que comprueba el propietario y ningún cliente autenticado global | [`app/almacenamiento.py`](../../app/almacenamiento.py), [`app/sql/02_historial.sql`](../../app/sql/02_historial.sql) | [`fase1/pruebas_integracion.md`](../fase1/pruebas_integracion.md) | cumple |
| 10 | Varias conversaciones por persona, recuperables al cerrar sesión y al volver | [`app/almacenamiento.py`](../../app/almacenamiento.py) | [`fase3/prueba_interfaz.md`](../fase3/prueba_interfaz.md) | cumple |
| 11 | Corpus legible por los usuarios autorizados, sin abrirlo a todos ni usar clave administrativa | [`app/sql/01_corpus.sql`](../../app/sql/01_corpus.sql) (`lectores_corpus`) | [`app/tests/test_integracion_recuperacion.py`](../../app/tests/test_integracion_recuperacion.py) | cumple |
| 12 | Persistir todo y elegir aparte el contexto que va al modelo | `TURNOS_CONTEXTO = 4` en [`app/sistema.py`](../../app/sistema.py) | `test_memoria_es_la_ventana_de_cuatro_turnos` en [`app/tests/test_sistema.py`](../../app/tests/test_sistema.py) | cumple |
| 13 | MCP con conexión real, argumentos, resultado, errores, procedencia, versión, transporte y permisos | Sección "Configuración del MCP" de [`app/README.md`](../../app/README.md) | [`fase3/prueba_interfaz.md`](../fase3/prueba_interfaz.md), `test_cliente_mcp_real_consulta_y_detecta_caida` | cumple |
| 14 | Acción sensible con contenido y destino visibles, aprobación por botón, comprobación en el código, registro y sin repeticiones | [`app/sistema.py`](../../app/sistema.py), [`app/sql/03_informes.sql`](../../app/sql/03_informes.sql) | `test_doble_clic_no_repite_la_escritura`; capturas 09 a 15 de [`fase3/capturas_v3/`](../fase3/capturas_v3/) | cumple |
| 15 | Configuración por variables de entorno, `.env.ejemplo` sin claves y variables de Supabase obligatorias | [`app/.env.ejemplo`](../../app/.env.ejemplo) | `test_sin_variable_obligatoria_no_arranca_y_no_muestra_valores`, `test_configuracion_nombra_las_variables_faltantes` | cumple |
| 16 | `.gitignore` con `.env`, `.env.*`, `!.env.ejemplo`, `.venv/`, `__pycache__/`, `*.pyc` y `*.sqlite3*` | [`.gitignore`](../../.gitignore) | Revisión de este archivo; ningún `.env` real está versionado | cumple |
| 17 | Notebooks, salidas, capturas y registros sin secretos, también en la historia de git | [`notebooks/`](../../notebooks/), [`evidencias/`](../) | Sección 4 de este archivo | cumple |
| 18 | README completo y reproducible | [`app/README.md`](../../app/README.md) | Sección 2 de este archivo | cumple |
| 19 | Instalación desde un clon limpio | [`app/README.md`](../../app/README.md) | [`clon_limpio.md`](clon_limpio.md) | parcial: probada en macOS; la ruta de PowerShell está documentada pero no se ejecutó |
| 20 | Despliegue con Root Directory `app`, escucha en `0.0.0.0` y `PORT`, secretos en el panel | [`render.yaml`](../../render.yaml) | [`fase4/pruebas_url_publica.md`](../fase4/pruebas_url_publica.md), [`app/tests/test_render.py`](../../app/tests/test_render.py) | cumple |
| 21 | Runtime de Node para el Filesystem MCP comprobado en el alojamiento | Build Command de [`render.yaml`](../../render.yaml), que instala el servidor con `npm ci` | El build en Render termina bien; la escritura del informe está probada en local en [`fase3/prueba_interfaz.md`](../fase3/prueba_interfaz.md) | pendiente: no hay una prueba registrada de escritura de un informe desde la URL pública |
| 22 | Recuperación de conversaciones desde la URL desplegada después de reiniciar | Supabase | [`fase4/pruebas_url_publica.md`](../fase4/pruebas_url_publica.md), prueba 2c | cumple |
| 23 | Pruebas: pregunta con fuentes, sin evidencia, entrada incompleta, herramienta, acción no permitida y falla técnica controlada | [`app/README.md`](../../app/README.md), "Pruebas y resultados observados" | [`fase3/`](../fase3/), [`fase4/`](../fase4/) | parcial: la falla técnica se probó en local, no en la URL pública |
| 24 | Guardado en Supabase, dos usuarios, dos conversaciones y aislamiento aun conociendo el identificador | [`app/sql/02_historial.sql`](../../app/sql/02_historial.sql) | [`fase1/pruebas_integracion.md`](../fase1/pruebas_integracion.md), [`fase4/pruebas_url_publica.md`](../fase4/pruebas_url_publica.md) | cumple |
| 25 | Variables requeridas y URL desplegada probadas | [`app/app.py`](../../app/app.py) | `test_sin_variable_obligatoria_no_arranca_y_no_muestra_valores`; sección 5 de este archivo | cumple |
| 26 | Lo esperado distinto de lo observado y los pendientes explicados | [`evidencias/`](../) | Cada archivo de prueba registra entrada, esperado, observado y estado | cumple |
| 27 | Presentación en `app/presentacion_proyecto.pdf` con problema, fuentes, recuperación, flujo, herramientas, persistencia, ejecución, resultados y limitaciones | [`app/presentacion_proyecto.pdf`](../../app/presentacion_proyecto.pdf) | Fuente en [`presentacion/presentacion_proyecto.html`](../../presentacion/presentacion_proyecto.html); 15 páginas revisadas una por una | cumple |
| 28 | Notebook consolidado y evaluaciones de los cortes anteriores | [`notebooks/`](../../notebooks/), [`evidencias/corte1/`](../corte1/), [`evidencias/corte2/`](../corte2/) | [`notebooks/README.md`](../../notebooks/README.md) | parcial: falta el notebook de la Clase 02, que no está en el material del equipo |
| 29 | Bitácora unificada con problema, arquitectura, decisiones, experimentos, errores, limitaciones, aportes y conclusiones, enlazada desde el README | [`BITACORA_PROYECTO.md`](../../BITACORA_PROYECTO.md) | Enlaces revisados en la sección 3 | parcial: los aportes sin respaldo están marcados para confirmar con el equipo |
| 30 | Prueba ciega del enrutador (requisito propio del proyecto) | [`fase4/preguntas_propias_axel.md`](../fase4/preguntas_propias_axel.md) | | pendiente |

## 2. Secciones de la plantilla del README

| Sección de la plantilla | Dónde está en [`app/README.md`](../../app/README.md) | Estado |
|---|---|---|
| Nombre del proyecto | Título | cumple |
| Problema, usuarios y alcance | "Problema, usuarios y alcance" | cumple |
| Arquitectura y procedencia del código | "Arquitectura y procedencia del código", con el recorrido y la tabla de archivos | cumple |
| Requisitos | "Requisitos": Python 3.13, sistemas probados, dependencias, servicios, Node y descarga de modelos | cumple |
| Instalación desde un clon limpio | "Instalación desde un clon limpio", Linux/macOS y PowerShell | cumple |
| Variables y secretos | "Variables y secretos", tabla con obligatoriedad | cumple |
| Preparación del corpus y de los datos | "Preparación del corpus y de los datos": corpus, embeddings, recuperación elegida, pasos únicos y lectores | cumple |
| Usuarios e historiales | "Usuarios e historiales": creación de usuarios, tablas, políticas y sesión | cumple |
| Configuración del MCP | "Configuración del MCP": MCP propio y Filesystem MCP | cumple |
| Ejecución local | "Ejecución local" | cumple |
| Despliegue de referencia en Render | "Despliegue de referencia en Render", con URL y commit evaluado | cumple |
| Pruebas y resultados observados | "Pruebas y resultados observados", con comandos y tabla | cumple |
| Seguridad, problemas frecuentes y limitaciones | Sección del mismo nombre | cumple |
| Presentación y evidencias | Sección del mismo nombre, con el PDF enlazado | cumple |
| Bitácora unificada del proyecto | Sección del mismo nombre, con el enlace | cumple |
| Equipo y referencias | Sección del mismo nombre | cumple |

## 3. Enlaces en los archivos Markdown

Se revisaron los 54 archivos `.md` versionados, incluido este, con un script que resuelve cada enlace relativo y cada ancla de encabezado.

| Revisión | Resultado |
|---|---|
| Enlaces relativos y anclas | 297 enlaces, 0 rotos |
| Enlaces a rutas locales o notas privadas (`[[...]]`, `/Users/`) | 0 |
| URL externas citadas | 2: el repositorio (HTTP 200) y la aplicación publicada (HTTP 200); las direcciones `127.0.0.1` son de ejecución local |

## 4. Secretos y rastros en toda la historia de git

Se revisaron los 115 commits de todas las ramas locales, con el contenido de cada cambio salvo imágenes, PDF, el archivo de vectores y los notebooks. Los notebooks se revisaron aparte.

| Búsqueda | Resultado |
|---|---|
| Claves de Groq (`gsk_`) | 0 |
| Tokens JWT (`eyJ...`) | 0 |
| Claves de Supabase (`sb_publishable_`, `sb_secret_`) | 1, el valor ficticio `sb_publishable_valor_...` de una prueba |
| URL de un proyecto de Supabase | 0 |
| `service_role` | 3: el README que dice que no se usa y dos pruebas que verifican que no aparezca |
| Correos | Solo direcciones ficticias de pruebas (`prueba.local`, `empresa.com`, `b.co`) |
| Rutas personales | 0 |
| Autores y committers | Los 115 con la dirección `noreply` de GitHub |
| Mensajes de commit con atribuciones, nombres de asistentes o caracteres decorativos | 0 |
| Archivos con nombres de asistentes | 1: `app/tests/test_estilo.py`, que contiene la lista de palabras prohibidas partida para que la propia prueba no la detecte |
| Notebooks versionados con nombres de asistentes o claves | 0 |
| Archivos `.env` reales versionados | 0; solo `app/.env.ejemplo` y `app/.env.pruebas.ejemplo` |
| Ramas publicadas | Solo `main` |

Los notebooks de los cortes anteriores se conservan byte a byte como se entregaron, con sus caracteres originales.

## 5. URL pública

| Comprobación | Resultado |
|---|---|
| `GET /` | HTTP 200 |
| `GET /config` | HTTP 200 |
| `GET /gradio_api/info` (API directa) | HTTP 404 con `{"detail": "No disponible."}` |
| Commit desplegado al cierre de esta revisión | `4b93b10`, despliegue de Render en estado `success` a las 02:55 UTC del 2026-11-23 (API de despliegues de GitHub) |

El código de la aplicación no cambió desde el commit `1ce46c5`, que es el evaluado en [`fase4/pruebas_url_publica.md`](../fase4/pruebas_url_publica.md). Los commits posteriores solo agregan documentación, evidencias, la presentación y un script de prueba del navegador.
