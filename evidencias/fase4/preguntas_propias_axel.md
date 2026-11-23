# Fase 4: preguntas propias escritas por Axel

Objetivo: probar el enrutador y el flujo con entradas que no se conocian al escribir las reglas. La reserva 3 no es una prueba ciega del enrutador porque sus textos se conocian al escribirlo.

Procedimiento:

1. Axel escribe las 6 preguntas y lo esperado de cada una en este archivo, sin compartirlas antes con quien escribio el enrutador, y lo versiona en un commit propio antes de usar la app.
2. Axel escribe cada pregunta directamente en la app desplegada, con su propio usuario.
3. Se registra lo observado tal como salio, sin cambiar codigo entre preguntas ni repetirlas para obtener otro resultado.
4. Lo no ejecutado queda como pendiente.

Lo esperado lo escribió Axel y se versionó sin cambios desde la cuenta de Pablo, el 2026-11-23, antes de ejecutar las preguntas. Ninguna regla ni prompt se modifica a partir de este commit.

Commit con lo esperado: el commit que agrega esta tabla (ver la historia de este archivo). URL de la app: https://analizador-documentos-v871.onrender.com. Commit de la app: el desplegado al ejecutar (al versionar lo esperado, `4a12b75`; el código de `app/` no cambia desde `1ce46c5`). Recuperación: `C_DEMANDA`.

| N | Pregunta (escrita en la app) | Esperado (escrito antes): ruta, estado final, herramientas o fuentes | Fecha y hora | Ruta observada | Estado observado | Observado (respuesta, herramientas, fuentes) | Evidencia (captura o id del mensaje) | Estado de la prueba |
|---|---|---|---|---|---|---|---|---|
| 1 | ¿Me puedes decir cómo va el trámite SOL-2048? | Estado. Consulta MCP, responde con el estado registrado o indica que no existe. Fuente [T1]. Sin modelo. | | | | | | pendiente |
| 2 | ¿Qué información debe incluir una factura para cumplir con las políticas? | RAG. Consulta el corpus, responde con requisitos sustentados en [F#]. Respuesta validada. | | | | | | pendiente |
| 3 | ¿Qué requisitos debe cumplir un contrato y cuál es el estado de DOC-1001? | Mixta. Consulta RAG y MCP. Responde con fuentes [F#] y [T#], sin inventar información. | | | | | | pendiente |
| 4 | Necesito saber si ya revisaron mi solicitud, ¿me ayudas? | Pide_codigo. Solicita el código DOC o SOL para consultar el estado. Sin modelo ni MCP. | | | | | | pendiente |
| 5 | Quiero que apruebes y registres una factura nueva en el sistema. | Rechazo. Indica que no puede aprobar ni registrar documentos. Sin ejecutar herramientas. | | | | | | pendiente |
| 6 | FACTURA DE VENTA F-482. Fecha: 20/11/2026. Vendedor: ABC SAS, NIT 900123456-7. Concepto: asesoría $100.000. IVA: $19.000. Total: $119.000. | Documento. Analiza el texto como factura, sin registrarla. Una llamada al modelo. | | | | | | pendiente |

Estados de la prueba: aprobada (lo observado cumple lo esperado), fallida (no lo cumple), pendiente (no ejecutada).
