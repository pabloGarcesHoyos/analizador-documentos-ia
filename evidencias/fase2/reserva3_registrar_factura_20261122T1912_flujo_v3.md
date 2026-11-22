# Fase 2: comprobacion del reintento alineado con el validador en reserva3_registrar_factura (flujo_v3)

Comando: `REGRESION_SALIDA=<carpeta> pytest -m reserva3 -k registrar_factura app/tests/test_reserva3_flujo.py`. Fecha: 2026-11-22T14:12:19.306190-05:00. Commit: `4f1234c`. Modelo: `openai/gpt-oss-20b`. Recuperacion: C_DEMANDA. GROQ_TPM 8000, GROQ_RPM 30.

Resultado: 0 de 1 aprobadas. Tokens del flujo: 2707.

Corrida unica de un solo caso para comprobar el cambio del commit 4f1234c (el reintento repite todas las reglas de citas). No es una prueba ciega ni reemplaza el resultado oficial de reserva_3, que es el 5 de 6 de reserva3_flujo_20261122T1901_flujo_v2. Resultado: sigue en ERROR_VALIDACION; en el reintento el modelo volvio a escribir la etiqueta solo al final, de modo que la primera frase quedo sin etiqueta propia. La columna de tokens anteriores viene de la corrida con flujo_v1.

| Caso | Entrada | Esperado (escrito antes de correr) | Ruta | Observado | Estado final | Llamadas al modelo | Reintento | Tokens esta corrida | Tokens corrida anterior | ms | Prueba |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `reserva3_registrar_factura` | ¿Puedo pedirle al analizador que registre una factura por mí? | reserva_3: Ruta RAG: busca en las políticas y responde (RESPONDIDA o PARCIAL) que el analizador solo consulta y no registra, citando [F#] de seguimiento_y_seguridad. | rag | ERROR_VALIDACION; herramientas: ninguna; fuentes: ninguna; respuesta: La respuesta generada no superó la validación de contrato y citas; no se muestra texto sin validar. | ERROR_VALIDACION | 2 | si | 2707 | 2604 | 2671.5 | fallida |
