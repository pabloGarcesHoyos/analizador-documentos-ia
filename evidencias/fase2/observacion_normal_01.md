# Observacion sobre el caso normal_01 de la regresion del corte 1

Entrada: "Factura de Venta No. F-9843. Fecha: 12/08/2026. Emisor: TechCorp S.A. Cliente: Juan Pérez. Concepto: Servicios de consultoría de software. Total a pagar: $1,500.00 USD."

Lo esperado del corte 1 (RESPUESTA_DIRECTA, clasificacion OK_VALIDADO) y el prompt del clasificador `analizador_v3` no se modificaron.

## Resultados observados

| Corrida | Fecha (UTC) | Decision del clasificador | Campos faltantes que informo | Estado final | Evidencia |
|---|---|---|---|---|---|
| Inicial | 2026-11-22 | OK_PIDE_ACLARACION | Condiciones de pago, direccion del emisor, direccion del cliente | RESPONDIDA (antes de la regla de coherencia) | `regresion_corte1.json` |
| 1 | 2026-11-22T17:11 | OK_PIDE_ACLARACION | Condiciones de pago, direccion del emisor, direccion del cliente | ACLARACION | `regresion_corte1_20261122T1711_corrida1.json` |
| 2 | 2026-11-22T17:21 | OK_PIDE_ACLARACION | Impuestos, numero de factura, fecha de vencimiento | ACLARACION | `regresion_corte1_20261122T1721_corrida2.json` |

En las tres corridas de hoy la decision del clasificador fue la misma, OK_PIDE_ACLARACION, distinta de la del corte 2 (RESPUESTA_DIRECTA en la corrida 2 de `rag_v3`). Entre la corrida 1 y la 2 cambio la lista de campos faltantes con el mismo modelo, el mismo prompt y `temperature=0`. Se registra como variacion del modelo: la temperatura cero no garantiza salidas identicas y Groq no expone una semilla.

## Observacion aparte

La factura de la entrada no incluye el NIT del emisor ni el desglose de impuestos. El corpus 2.0 (`politicas_facturacion.md`, seccion Requisitos de contabilizacion) exige NIT del emisor, fecha de expedicion, desglose de impuestos y total mayor que cero para contabilizar una factura. La expectativa del corte 1 para este caso se fijo antes de ese corpus y se conserva sin cambios.
