# Fase 1: pruebas de integracion con Supabase

Comando: `pytest -m integracion`. Fecha: 2026-11-22T11:39:34.104668-05:00. Commit: `50dd897`. Resultado: 8 de 8 aprobadas.

Usuarios: A (lector autorizado del corpus) y B (sin autorizacion), creados en Supabase Auth. Las credenciales no forman parte de esta evidencia.

| Prueba | Esperado | Observado | Estado | Segundos |
|---|---|---|---|---|
| `test_cada_usuario_es_quien_dice_su_token` | auth.get_user devuelve el id de A con el token de A y el de B con el de B; un token alterado produce SesionInvalida. | Los identificadores coincidieron con cada token y el token alterado fue rechazado. | aprobada | 1.93 |
| `test_turno_completo_y_orden` | Dos turnos guardados se recuperan en orden pregunta 1, respuesta 1, pregunta 2, respuesta 2, con las fuentes y el estado de cada respuesta. | Orden exacto; las fuentes recuperadas son iguales a las guardadas y el segundo turno conserva el estado ACLARAR. | aprobada | 2.63 |
| `test_dos_conversaciones_de_la_misma_persona` | A crea dos conversaciones y ambas aparecen en su listado. | Las dos conversaciones aparecieron en el listado de A. | aprobada | 1.22 |
| `test_b_no_lee_ni_lista_la_conversacion_de_a` | B no ve la conversacion de A en su listado; cargar_mensajes devuelve AccesoDenegado; por la API directa con el UUID obtiene 0 conversaciones y 0 mensajes. | Se cumplieron las cuatro comprobaciones. | aprobada | 2.62 |
| `test_b_no_inserta_en_la_conversacion_de_a` | guardar_turno de B en la conversacion de A produce AccesoDenegado; por la API directa, insertar con el usuario de B o con el de A falla con 42501 o 23503; la conversacion de A queda sin mensajes. | Los dos intentos directos fueron rechazados por Supabase y la conversacion de A quedo vacia. | aprobada | 2.13 |
| `test_decision_de_informe_unica` | La aprobacion se registra una vez y repetirla produce AccionYaRegistrada; B no aprueba ni fija el resultado de una accion de A; el resultado se fija una sola vez. | Primera aprobacion aceptada y duplicado rechazado; los dos intentos de B rechazados; ejecutada aceptado y el segundo resultado rechazado. | aprobada | 4.59 |
| `test_lector_autorizado_busca_en_el_corpus_y_el_otro_no` | A, lector autorizado, obtiene 10 resultados de analizador_buscar_fragmentos_autorizado y ve los 20 fragmentos del corpus 2.0; B obtiene 0. | A obtuvo 10 resultados y vio 20 fragmentos; B obtuvo una lista vacia. | aprobada | 0.84 |
| `test_anonimo_sin_acceso` | Sin sesion, las cinco tablas responden con error de permisos o con 0 filas. | Ninguna tabla devolvio filas al cliente anonimo. | aprobada | 0.78 |
