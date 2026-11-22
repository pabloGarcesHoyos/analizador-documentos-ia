# Analizador de Documentos

Aplicación web para consultar políticas de facturación, contratos y documentos de identificación, revisar el estado de expedientes y generar informes con fuentes citadas.

Proyecto del curso Inteligencia Artificial Generativa y Sistemas Inteligentes, EAM 2026-II. Equipo: Pablo Garcés Hoyos y Axel Dereck Gutiérrez.

## Qué hace

- Responde preguntas sobre políticas con recuperación híbrida (BM25 y embeddings, fusión RRF y reordenamiento) sobre un corpus ficticio guardado en Supabase con pgvector. Cada frase de la respuesta lleva la cita del pasaje que la respalda.
- Consulta el estado de documentos `DOC-XXXX` y solicitudes `SOL-XXXX` con un servidor MCP propio de solo lectura.
- Clasifica el texto de un documento con el contrato del corte 1.
- Propone un informe en Markdown que solo se escribe, con el servidor Filesystem MCP, si el usuario lo aprueba.
- Inicio de sesión con Supabase Auth. Las conversaciones de cada usuario se guardan con seguridad a nivel de fila: nadie lee ni escribe las de otro.

## Estructura

```
app/                aplicación (Root Directory en Render)
  app.py            interfaz Gradio
  sistema.py        enrutador, contratos, validación y clientes MCP
  almacenamiento.py autenticación, conversaciones y mensajes en Supabase
  recuperacion.py   recuperación híbrida con modelos ONNX
  servidor_mcp.py   servidor MCP de consulta de estado
  cargar_corpus.py  carga única del corpus
  sql/              esquema, políticas de seguridad y funciones
  corpus/           documentos ficticios del corpus
  tests/            pruebas
evidencias/         resultados de las pruebas por fase
render.yaml         configuración de despliegue en Render
```

## Ejecución local

```
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-pruebas.txt
cp app/.env.ejemplo app/.env
.venv/bin/python app/descargar_modelos.py
npm ci --prefix app/mcp_archivos --omit=dev
.venv/bin/python app/app.py
```

Completa `app/.env` con los datos de tu proyecto de Supabase y tu clave de Groq. Ejecuta los archivos de `app/sql/` en el SQL Editor y carga el corpus con `python app/cargar_corpus.py`.

## Pruebas

```
.venv/bin/python -m pytest
```

Las pruebas de integración con Supabase y Groq se marcan aparte (`-m integracion`, `-m groq`) y necesitan `app/.env.pruebas`.

## Estado

La documentación completa de arquitectura, decisiones, evaluación y despliegue se agrega en la última fase del proyecto.
