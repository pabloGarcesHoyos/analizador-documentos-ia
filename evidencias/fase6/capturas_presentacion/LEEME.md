# Capturas de la presentación

Fecha: 2026-11-23 (UTC). URL: https://analizador-documentos-v871.onrender.com, con el commit `4b93b10` desplegado. Usuario: demostración. Navegador: Chromium con Playwright 1.64.1, ventana de 1366 px de ancho y escala 2.

| Archivo | Entrada | Observado | Uso |
|---|---|---|---|
| [`demo_mixta_pagina.png`](demo_mixta_pagina.png) | "¿Qué requisitos tiene una factura y en qué estado está DOC-1001?" en una conversación nueva | Rótulo "Respondida con documentos y datos del registro.", frase del registro con `[T1]` y requisitos con `[F1]` y `[F2]`, en 27,6 s. El correo de la sesión está cubierto con un recuadro gris. | Diapositiva 9 |
| [`demo_mixta_respuesta.png`](demo_mixta_respuesta.png) | La misma conversación, abierta de nuevo desde la lista | Respuesta completa con el bloque de fuentes y el de consultas. Para que la respuesta entrara entera en la imagen, se quitó solo para la captura el alto fijo del chat; el contenido no cambia. | Diapositiva 10 |

Las credenciales se leyeron de `app/.env.pruebas` dentro del script y no se imprimieron. Antes de guardar, el script comprobó que el texto visible no tuviera la contraseña, tokens ni el correo sin cubrir.
