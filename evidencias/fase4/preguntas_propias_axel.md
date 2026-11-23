# Fase 4: preguntas propias escritas por Axel

Objetivo: probar el enrutador y el flujo con entradas que no se conocian al escribir las reglas. La reserva 3 no es una prueba ciega del enrutador porque sus textos se conocian al escribirlo.

Procedimiento:

1. Axel escribe las 6 preguntas y lo esperado de cada una en este archivo, sin compartirlas antes con quien escribio el enrutador, y lo versiona en un commit propio antes de usar la app.
2. Axel escribe cada pregunta directamente en la app desplegada, con su propio usuario.
3. Se registra lo observado tal como salio, sin cambiar codigo entre preguntas ni repetirlas para obtener otro resultado.
4. Lo no ejecutado queda como pendiente.

Lo esperado lo escribió Axel y se versionó sin cambios desde la cuenta de Pablo, el 2026-11-23, en el commit `9b81c9a`, antes de ejecutar las preguntas. Ninguna regla ni prompt se modificó a partir de ese commit.

Ejecución: 2026-11-23 entre las 03:38 y las 03:41 UTC, con Playwright (Chromium visible, `slow_mo` de 400 ms) en presencia de Axel y con su usuario de Supabase Auth, sin conversaciones previas. Cada pregunta se escribió una sola vez, en una conversación nueva, sin cambios de código entre preguntas.

URL de la app: https://analizador-documentos-v871.onrender.com. Commit desplegado en Render: `4a12b75` (despliegue `success`). El último commit de `main` era `9b81c9a`; entre los dos no cambia ningún archivo de `app/`, y Render no despliega cambios fuera de la carpeta raíz `app`. Recuperación: `C_DEMANDA`.

La ruta, el estado guardado, las llamadas al modelo y los tokens de cada turno se leyeron de la traza guardada en Supabase, con el token de Axel. El tiempo va desde el clic en Enviar hasta que la respuesta termina, e incluye el `slow_mo`. Un primer intento de ejecución se detuvo al iniciar sesión, porque el servicio estaba despertando y el formulario tardó más de 30 s; no se envió ninguna pregunta (Axel seguía con 0 conversaciones) y se volvió a iniciar con una espera de carga de 3 minutos.

| N | Pregunta (escrita en la app) | Esperado (escrito antes): ruta, estado final, herramientas o fuentes | Fecha y hora | Ruta observada | Estado observado | Observado (respuesta, herramientas, fuentes) | Evidencia (captura o id del mensaje) | Estado de la prueba |
|---|---|---|---|---|---|---|---|---|
| 1 | ¿Me puedes decir cómo va el trámite SOL-2048? | Estado. Consulta MCP, responde con el estado registrado o indica que no existe. Fuente [T1]. Sin modelo. | 2026-11-23 03:38:32 UTC (34.2 s) | mixta | PARCIAL | Rótulo "Respondida en parte con documentos y datos del registro: revisa la limitación indicada." Respuesta: "La solicitud SOL-2048 no existe en el registro de seguimiento de expedientes [T1]. ¿Sobre qué trámite o tipo de documento necesitas ayuda?" Consulta MCP de SOL-2048 (encontrado: no), 1 llamada al modelo, sin fuentes [F#]. Tokens del turno: 1300. | [axel_01.png](capturas_axel/axel_01.png); conversación `18792544` | fallida |
| 2 | ¿Qué información debe incluir una factura para cumplir con las políticas? | RAG. Consulta el corpus, responde con requisitos sustentados en [F#]. Respuesta validada. | 2026-11-23 03:39:11 UTC (22.5 s) | rag | RESPONDIDA | Rótulo "Respondida con evidencia de los documentos." Requisitos (NIT del emisor, fecha de expedición, desglose de impuestos y total mayor que cero) con [F1] y consecuencia de su falta con [F3], ambas de politicas_facturacion.md. 1 llamada al modelo, sin consultas MCP. Tokens del turno: 1353. | [axel_02.png](capturas_axel/axel_02.png); conversación `91e9238c` | aprobada |
| 3 | ¿Qué requisitos debe cumplir un contrato y cuál es el estado de DOC-1001? | Mixta. Consulta RAG y MCP. Responde con fuentes [F#] y [T#], sin inventar información. | 2026-11-23 03:39:38 UTC (31.7 s) | mixta | RESPONDIDA | Rótulo "Respondida con documentos y datos del registro." DOC-1001 verificado_y_contabilizado [T1]; requisitos del contrato de prestación de servicios [F1] y consecuencia de la falta de vigencia o firma [F2], de gestion_contratos.md. 1 llamada al modelo y 1 consulta MCP. Tokens del turno: 1339. | [axel_03.png](capturas_axel/axel_03.png); conversación `4a03f899` | aprobada |
| 4 | Necesito saber si ya revisaron mi solicitud, ¿me ayudas? | Pide_codigo. Solicita el código DOC o SOL para consultar el estado. Sin modelo ni MCP. | 2026-11-23 03:40:14 UTC (5.5 s) | pide_codigo | ACLARACION | Rótulo "Se necesita una aclaración para continuar." Respuesta: "Para consultar el estado necesito el código del documento o de la solicitud, con formato DOC-XXXX o SOL-XXXX." 0 llamadas al modelo, sin MCP. Tokens del turno: 0. | [axel_04.png](capturas_axel/axel_04.png); conversación `5c9f7ab7` | aprobada |
| 5 | Quiero que apruebes y registres una factura nueva en el sistema. | Rechazo. Indica que no puede aprobar ni registrar documentos. Sin ejecutar herramientas. | 2026-11-23 03:40:24 UTC (6.8 s) | libre | RECHAZO | Rótulo "Solicitud rechazada: el analizador solo consulta información." Respuesta: "Lo siento, pero no puedo ayudar con esa solicitud." Sin herramientas; 1 llamada al modelo. Tokens del turno: 447. | [axel_05.png](capturas_axel/axel_05.png); conversación `c46c61cf` | aprobada, con observación |
| 6 | FACTURA DE VENTA F-482. Fecha: 20/11/2026. Vendedor: ABC SAS, NIT 900123456-7. Concepto: asesoría $100.000. IVA: $19.000. Total: $119.000. | Documento. Analiza el texto como factura, sin registrarla. Una llamada al modelo. | 2026-11-23 03:40:35 UTC (5.6 s) | documento | ACLARACION | Rótulo "Se necesita una aclaración para continuar." Respuesta: "Para continuar necesitamos: Cliente [T1]." Clasificación: factura, riesgo bajo, campo faltante Cliente; no se registró nada. 1 llamada al modelo. Tokens del turno: 851. | [axel_06.png](capturas_axel/axel_06.png); conversación `d3600572` | aprobada |

Estados de la prueba: aprobada (lo observado cumple lo esperado), fallida (no lo cumple), pendiente (no ejecutada).

## Resultado

5 aprobadas (una con observación) y 1 fallida. Tokens de Groq de las 6 preguntas: 5.290.

- **1, fallida.** Lo esperado era la ruta estado sin modelo; salió mixta con 1 llamada. El enrutador trata "puedes" como señal de pregunta de políticas (`RE_POLITICA` incluye `puede\w*`), y una pregunta con código y esa señal va a la ruta mixta. El dato del registro sí es correcto: SOL-2048 no existe, con [T1].
- **5, aprobada con observación.** Quedó a revisar al registrarla, porque "Rechazo" en lo esperado podía leerse como ruta o como estado final. Decisión de Axel, el 2026-11-23: aprobada, porque el rechazo ocurrió sin herramientas y el rótulo mostrado dice que el analizador solo consulta información, que es lo que esperaba. Observación, que queda como limitación documentada: el texto de la respuesta es genérico ("no puedo ayudar con esa solicitud") y la entrada pasó por la ruta libre, con una llamada al modelo, y no por el rechazo directo, porque empieza con "Quiero que apruebes" y el enrutador solo rechaza sin modelo cuando la entrada empieza con la orden.
- **6, aprobada.** Lo esperado no fijaba un estado final. El resultado fue aclaración, porque el clasificador marcó como faltante el cliente.
