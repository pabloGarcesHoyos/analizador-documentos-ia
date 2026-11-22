import asyncio
import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import gradio as gr
import pytest

import almacenamiento as al
import app as ap
import sistema as si
from supabase_falso import BaseFalsa
from test_sistema import LLMGuionado, MCPFalso, RecuperadorFalso, rag

CLAVES = {"a@prueba.local": "clave-a-secreta", "b@prueba.local": "clave-b-secreta"}
MIXTA = "¿Qué requisitos tiene una factura y en qué estado está DOC-1001?"


class Reloj:
    def __init__(self):
        self.ahora = 1_000_000.0

    def __call__(self):
        return self.ahora


class AutenticacionFalsa:
    def __init__(self, base, reloj):
        self.base = base
        self.reloj = reloj
        self.renovables = {}
        self.cerradas = []
        self.contador = 0

    def _emitir(self, correo, usuario_id):
        self.contador += 1
        token = f"token-{correo[0]}-{self.contador}"
        self.base.usuarios[token] = usuario_id
        renovacion = f"renovacion-{correo[0]}-{self.contador}"
        self.renovables[renovacion] = (correo, usuario_id)
        return al.Sesion(token, renovacion, self.reloj() + 3600, usuario_id, correo)

    def iniciar_sesion(self, correo, clave):
        if CLAVES.get(correo) != clave:
            raise al.CredencialesInvalidas("No se pudo iniciar sesión: revisa el correo y la contraseña.")
        return self._emitir(correo, self.base.usuarios[f"token-{correo[0]}"])

    def refrescar(self, renovacion):
        if renovacion not in self.renovables:
            raise al.SesionInvalida("La sesión venció y no se pudo renovar.")
        correo, usuario_id = self.renovables.pop(renovacion)
        return self._emitir(correo, usuario_id)

    def cerrar_sesion(self, access_token, refresh_token):
        self.cerradas.append(access_token)


class EscritorDisco:
    def __init__(self, error=None):
        self.error = error
        self.escrituras = []

    async def escribir(self, ruta, contenido):
        await asyncio.sleep(0.01)
        if self.error:
            raise self.error
        self.escrituras.append(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8")


@pytest.fixture
def entorno(tmp_path):
    return crear_entorno(tmp_path)


def crear_entorno(tmp_path):
    reloj = Reloj()
    base = BaseFalsa({"token-a": str(uuid.uuid4()), "token-b": str(uuid.uuid4())})
    configuracion = si.ConfiguracionSistema(al.ConfiguracionSupabase("https://p.supabase.co", "sb_publishable_x"), "clave-de-prueba", "corpus",
                                            str(uuid.uuid4()), carpeta_informes=tmp_path / "informes", max_segundos=5)
    almacen = al.Almacenamiento(configuracion.supabase, fabrica=base.fabrica)
    llm, mcp, escritor = LLMGuionado(rag=[rag() for _ in range(6)]), MCPFalso(), EscritorDisco()
    sistema = si.Sistema(configuracion, almacen=almacen, recuperador=RecuperadorFalso(), llm=llm, mcp_estado=mcp, escritor=escritor,
                         fabrica_fuente=lambda token: "fuente")
    autenticacion = AutenticacionFalsa(base, reloj)
    return SimpleNamespace(base=base, almacen=almacen, sistema=sistema, llm=llm, mcp=mcp, escritor=escritor, reloj=reloj,
                           autenticacion=autenticacion, interfaz=ap.Interfaz(autenticacion, almacen, sistema, reloj=reloj))


def entrar(e, correo="a@prueba.local"):
    return e.interfaz.entrar(correo, CLAVES[correo])["sesion"]


def responder(e, sesion, texto, conversacion=None, chat=None):
    return asyncio.run(e.interfaz.responder(sesion, conversacion, texto, chat or []))


def test_inicio_de_sesion_correcto_lista_solo_lo_propio(entorno):
    entorno.almacen.crear_conversacion("token-a", "Conversación de A")
    entorno.almacen.crear_conversacion("token-b", "Conversación de B")
    salida = entorno.interfaz.entrar("a@prueba.local", CLAVES["a@prueba.local"])
    assert salida["sesion"]["access_token"].startswith("token-a-") and salida["sesion"]["refresh_token"].startswith("renovacion-a-")
    assert salida["clave"] == "" and salida["vista_app"]["visible"] and not salida["vista_login"]["visible"]
    assert [titulo for titulo, _ in salida["lista"]["choices"]] == ["Conversación de A"]
    assert "clave-a-secreta" not in json.dumps(salida, default=str)


@pytest.mark.parametrize("correo, clave", [("a@prueba.local", "otra"), ("nadie@prueba.local", "x"), ("", "")])
def test_inicio_de_sesion_fallido_no_deja_sesion_ni_contrasena(entorno, correo, clave):
    salida = entorno.interfaz.entrar(correo, clave)
    assert salida["sesion"] is None and salida["clave"] == "" and "No se pudo iniciar sesión" in salida["aviso_login"]
    assert "vista_app" not in salida and (not clave or clave not in json.dumps(salida, default=str))


def test_contrasena_no_queda_en_estado_ni_en_la_traza(entorno):
    sesion = entrar(entorno)
    salida = responder(entorno, sesion, "¿Qué datos debe traer una factura?")
    guardado = json.dumps(entorno.base.tablas, default=str) + json.dumps(sesion) + json.dumps(salida, default=str)
    assert "clave-a-secreta" not in guardado and set(sesion) == {"access_token", "refresh_token", "expira_en", "usuario_id", "correo"}


def test_token_por_vencer_se_renueva_antes_de_usarlo(entorno):
    sesion = entrar(entorno)
    conversacion = entorno.almacen.crear_conversacion(sesion["access_token"], "Uno")["id"]
    entorno.reloj.ahora += 3600 - 30
    salida = entorno.interfaz.seleccionar(sesion, conversacion)
    assert salida["sesion"]["access_token"] != sesion["access_token"] and salida["conversacion"] == conversacion
    assert salida["sesion"]["correo"] == "a@prueba.local"


def test_token_vencido_sin_renovacion_vuelve_al_inicio(entorno):
    sesion = entrar(entorno)
    conversacion = entorno.almacen.crear_conversacion(sesion["access_token"], "Uno")["id"]
    entorno.autenticacion.renovables.clear()
    entorno.reloj.ahora += 4000
    for salida in (entorno.interfaz.seleccionar(sesion, conversacion), responder(entorno, sesion, "¿Qué datos debe traer una factura?", conversacion)):
        assert salida["sesion"] is None and salida["vista_login"]["visible"] and salida["aviso_login"] == ap.AVISO_VENCIDA
    assert entorno.llm.llamadas == []


def test_cerrar_sesion_limpia_el_estado(entorno):
    sesion = entrar(entorno)
    salida = entorno.interfaz.salir(sesion)
    assert salida["sesion"] is None and salida["conversacion"] is None and salida["propuesta"] is None and salida["chat"] == []
    assert salida["vista_login"]["visible"] and entorno.autenticacion.cerradas == [sesion["access_token"]]


def test_cambio_de_conversacion_carga_desde_supabase(entorno):
    sesion = entrar(entorno)
    token = sesion["access_token"]
    uno = entorno.almacen.crear_conversacion(token, "Uno")["id"]
    dos = entorno.almacen.crear_conversacion(token, "Dos")["id"]
    entorno.almacen.guardar_turno(token, uno, "pregunta uno", "respuesta uno", "RESPONDIDA")
    entorno.almacen.guardar_turno(token, dos, "pregunta dos", "respuesta dos", "ACLARACION")
    salida = entorno.interfaz.seleccionar(sesion, uno)
    assert [m["content"] for m in salida["chat"]] == ["pregunta uno", f"**{ap.ESTADOS['RESPONDIDA']}**\n\nrespuesta uno"]
    salida = entorno.interfaz.seleccionar(sesion, dos)
    assert salida["chat"][0]["content"] == "pregunta dos" and ap.ESTADOS["ACLARACION"] in salida["indicador"]
    entorno.almacen.guardar_turno(token, uno, "pregunta nueva", "respuesta nueva", "RESPONDIDA")
    assert entorno.interfaz.seleccionar(sesion, uno)["chat"][-2]["content"] == "pregunta nueva"


def test_conversacion_ajena_no_se_carga(entorno):
    ajena = entorno.almacen.crear_conversacion("token-a", "De A")["id"]
    entorno.almacen.guardar_turno("token-a", ajena, "secreto de A", "respuesta", "RESPONDIDA")
    salida = entorno.interfaz.seleccionar(entrar(entorno, "b@prueba.local"), ajena)
    assert salida["chat"] == [] and salida["conversacion"] is None and salida["indicador"] == ap.ESTADOS["ACCESO_DENEGADO"]
    assert "secreto de A" not in json.dumps(salida, default=str)


def test_dos_sesiones_simultaneas_quedan_aisladas(entorno):
    sesion_a, sesion_b = entrar(entorno), entrar(entorno, "b@prueba.local")

    async def ambas():
        return await asyncio.gather(entorno.interfaz.responder(sesion_a, None, "¿Qué datos debe traer una factura? (A)", []),
                                    entorno.interfaz.responder(sesion_b, None, "¿Qué datos debe traer una factura? (B)", []))

    salida_a, salida_b = asyncio.run(ambas())
    assert salida_a["conversacion"] != salida_b["conversacion"]
    assert [v for _, v in salida_a["lista"]["choices"]] == [salida_a["conversacion"]]
    assert [v for _, v in salida_b["lista"]["choices"]] == [salida_b["conversacion"]]
    assert entorno.interfaz.seleccionar(sesion_b, salida_a["conversacion"])["chat"] == []
    mensajes_b = entorno.almacen.cargar_mensajes(sesion_b["access_token"], salida_b["conversacion"])
    assert [m["contenido"] for m in mensajes_b if m["rol"] == "usuario"] == ["¿Qué datos debe traer una factura? (B)"]
    assert not any(k in vars(entorno.interfaz) for k in ("sesion", "token", "conversacion"))


def test_primera_pregunta_crea_la_conversacion_con_titulo_automatico(entorno):
    sesion = entrar(entorno)
    texto = "¿Qué requisitos debe cumplir una factura de venta para que el área contable la pueda contabilizar sin devolverla?"
    salida = responder(entorno, sesion, texto)
    conversaciones = entorno.almacen.listar_conversaciones(sesion["access_token"])
    assert conversaciones[0]["id"] == salida["conversacion"] and conversaciones[0]["titulo"] == ap.titulo_automatico(texto)
    assert ap.titulo_automatico(texto).endswith("...") and len(ap.titulo_automatico(texto)) <= ap.LARGO_TITULO + 3
    assert ap.titulo_automatico("  Hola\n  mundo ") == "Hola mundo" and salida["entrada"]["value"] == ""
    segunda = responder(entorno, sesion, "¿Y el NIT?", salida["conversacion"], salida["chat"])
    assert segunda["conversacion"] == salida["conversacion"] and len(entorno.almacen.listar_conversaciones(sesion["access_token"])) == 1


def test_nueva_conversacion_no_crea_nada_hasta_la_primera_pregunta(entorno):
    sesion = entrar(entorno)
    salida = entorno.interfaz.nueva()
    assert salida["conversacion"] is None and salida["chat"] == [] and salida["propuesta"] is None
    assert entorno.almacen.listar_conversaciones(sesion["access_token"]) == []


def test_respuesta_muestra_fuentes_y_resultados_de_herramientas(entorno):
    salida = responder(entorno, entrar(entorno), MIXTA)
    principal, fuentes, consultas = salida["chat"][1:]
    assert ap.ESTADOS["RESPONDIDA"] in principal["content"] and "[T1]" in principal["content"] and "[F1]" in principal["content"]
    assert fuentes["metadata"]["title"] == "Fuentes: [F1]" and "Documento: politicas_facturacion" in fuentes["content"] and "Sección:" in fuentes["content"]
    assert "> " in fuentes["content"]
    assert consultas["metadata"]["title"] == "Consultas: [T1]" and "Código consultado: DOC-1001" in consultas["content"]
    assert "Estado: verificado_y_contabilizado" in consultas["content"] and salida["indicador"] == ap.ESTADOS["RESPONDIDA"]


def test_estados_con_texto_claro_y_distinto():
    for estado in ("RESPONDIDA", "ACLARACION", "SIN_EVIDENCIA", "RECHAZO", "ERROR_TECNICO", "ERROR_VALIDACION"):
        assert ap.texto_estado(estado) != "Estado desconocido."
    assert len(set(ap.ESTADOS.values())) == len(ap.ESTADOS)
    assert "No significa que falte información" in ap.ESTADOS["ERROR_TECNICO"] and "evidencia" not in ap.ESTADOS["ERROR_TECNICO"].lower()


def test_error_tecnico_se_presenta_como_tal(entorno):
    entorno.sistema.mcp_estado = MCPFalso(error=si.ErrorTecnico("mcp"))
    salida = responder(entorno, entrar(entorno), "¿Cómo va DOC-1001?")
    assert salida["indicador"] == ap.ESTADOS["ERROR_TECNICO"] and ap.ESTADOS["ERROR_TECNICO"] in salida["chat"][-1]["content"]
    assert "Detalle: " + si.DETALLE_TECNICO["mcp"] in salida["chat"][-1]["content"]


def test_entrada_se_bloquea_mientras_atiende(entorno):
    bloqueo = entorno.interfaz.bloquear(None, "Hola", [])
    assert all(not bloqueo[n]["interactive"] for n in ("entrada", "enviar", "nueva", "salir", "lista"))
    assert bloqueo["chat"] == [{"role": "user", "content": "Hola"}] and bloqueo["indicador"] == "Procesando tu consulta…"
    assert entorno.interfaz.bloquear(None, "   ", []) == {}
    assert responder(entorno, entrar(entorno), "   ") == {"indicador": "Escribe una pregunta antes de enviar."}


def proponer(entorno):
    sesion = entrar(entorno)
    salida = responder(entorno, sesion, "¿Qué datos debe traer una factura? Haz un informe")
    assert salida["informe"]["visible"] and salida["propuesta"]["destino"] in salida["informe_destino"]
    assert salida["informe_contenido"] == salida["propuesta"]["contenido"] and salida["aprobar"]["interactive"]
    return sesion, salida["propuesta"]


def test_aprobar_registra_escribe_verifica_y_ofrece_descarga(entorno):
    sesion, propuesta = proponer(entorno)
    salida = asyncio.run(entorno.interfaz.aprobar(sesion, propuesta))
    ruta = Path(salida["archivo"]["value"])
    assert salida["archivo"]["visible"] and salida["propuesta"] is None and "no guarda los informes" in salida["aviso_informe"]
    assert hashlib.sha256(ruta.read_bytes()).hexdigest() == propuesta["huella"] and ruta.name == propuesta["destino"]
    escrita = entorno.escritor.escrituras[0]
    assert escrita != ruta and escrita.read_bytes() == ruta.read_bytes() and Path(ap.tempfile.gettempdir()).resolve() in ruta.resolve().parents
    acciones = entorno.base.tablas["acciones_informe"]
    assert [(a["decision"], a["resultado"]) for a in acciones] == [("aprobada", "ejecutada")]


def test_doble_clic_no_repite_la_escritura(entorno):
    sesion, propuesta = proponer(entorno)

    async def dos_clics():
        return await asyncio.gather(entorno.interfaz.aprobar(sesion, propuesta), entorno.interfaz.aprobar(sesion, propuesta))

    salidas = asyncio.run(dos_clics())
    tardia = asyncio.run(entorno.interfaz.aprobar(sesion, propuesta))
    assert len(entorno.escritor.escrituras) == 1 and len(entorno.base.tablas["acciones_informe"]) == 1
    assert sum("archivo" in s for s in salidas) == 1 and "no se repite" in tardia["aviso_informe"]
    assert all(not v["interactive"] for v in entorno.interfaz.bloquear_informe().values())


def test_rechazar_registra_y_no_escribe(entorno):
    sesion, propuesta = proponer(entorno)
    salida = asyncio.run(entorno.interfaz.rechazar(sesion, propuesta))
    assert salida["propuesta"] is None and "Rechazo registrado" in salida["aviso_informe"]
    despues = asyncio.run(entorno.interfaz.aprobar(sesion, propuesta))
    assert "no se repite" in despues["aviso_informe"] and entorno.escritor.escrituras == []
    assert [(a["decision"], a["resultado"]) for a in entorno.base.tablas["acciones_informe"]] == [("rechazada", None)]
    assert asyncio.run(entorno.interfaz.aprobar(sesion, None))["aviso_informe"].startswith("Esta propuesta ya fue atendida")


def test_falla_al_escribir_queda_fallida_sin_reintento(entorno):
    entorno.sistema.escritor = EscritorDisco(error=si.ErrorTecnico("mcp_archivos"))
    sesion, propuesta = proponer(entorno)
    salida = asyncio.run(entorno.interfaz.aprobar(sesion, propuesta))
    assert "registrado como fallido" in salida["aviso_informe"] and "archivo" not in salida
    assert [(a["decision"], a["resultado"]) for a in entorno.base.tablas["acciones_informe"]] == [("aprobada", "fallida")]


ENTORNO = {"SUPABASE_URL": "https://p.supabase.co", "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_valor_privado", "GROQ_API_KEY": "gsk_valorprivado",
           "CORPUS_ID": "corpus", "CORPUS_PROPIETARIO_ID": str(uuid.uuid4())}


def test_configuracion_obligatoria_y_puerto():
    configuracion, servidor, puerto = ap.cargar_configuracion({**ENTORNO, "GRADIO_SERVER_NAME": "0.0.0.0", "PORT": "10000"})
    assert (servidor, puerto) == ("0.0.0.0", 10000) and configuracion.corpus_id == "corpus"
    assert ap.cargar_configuracion(ENTORNO)[1:] == ("127.0.0.1", 7860)
    with pytest.raises(al.ConfiguracionInvalida, match="PORT"):
        ap.cargar_configuracion({**ENTORNO, "PORT": "abc"})


def test_sin_variable_obligatoria_no_arranca_y_no_muestra_valores(monkeypatch):
    monkeypatch.setattr(si, "cargar_entorno", lambda: {k: v for k, v in ENTORNO.items() if k != "GROQ_API_KEY"})
    with pytest.raises(SystemExit) as salida:
        ap.main()
    mensaje = str(salida.value.code)
    assert "GROQ_API_KEY" in mensaje and "sb_publishable_valor_privado" not in mensaje and "corpus" not in mensaje.replace("CORPUS", "")


def test_arranque_escucha_en_el_entorno_sin_share(monkeypatch, entorno):
    capturado = {}
    monkeypatch.setattr(si, "cargar_entorno", lambda: {**ENTORNO, "GRADIO_SERVER_NAME": "0.0.0.0", "PORT": "10000"})
    monkeypatch.setattr(si, "Sistema", lambda configuracion: entorno.sistema)
    monkeypatch.setattr("descargar_modelos.asegurar", lambda: None)
    monkeypatch.setattr(gr.Blocks, "queue", lambda self, **opciones: capturado.update(cola=opciones) or self)
    monkeypatch.setattr(gr.Blocks, "launch", lambda self, **opciones: capturado.update(lanzamiento=opciones))
    ap.main()
    assert capturado["lanzamiento"]["share"] is False and capturado["lanzamiento"]["server_name"] == "0.0.0.0"
    assert capturado["lanzamiento"]["server_port"] == 10000 and capturado["cola"]["default_concurrency_limit"] == ap.CONCURRENCIA_GENERAL
    assert capturado["cola"]["api_open"] is False


def test_la_interfaz_se_construye_y_la_atencion_va_de_a_una(entorno):
    demo = ap.construir(entorno.interfaz)
    atencion = [d for d in demo.fns.values() if d.concurrency_id == "atencion"]
    assert atencion and all(d.concurrency_limit == ap.CONCURRENCIA_ATENCION for d in atencion)
    assert all(d.api_visibility == "private" for d in demo.fns.values())


def comparar_en_vivo_y_recargada(e, sesion, texto):
    salida = responder(e, sesion, texto)
    recargada = e.interfaz.seleccionar(sesion, salida["conversacion"])
    assert recargada["chat"] == salida["chat"]
    return salida["chat"]


def test_conversacion_recargada_identica_con_fuentes_y_consultas(entorno):
    chat = comparar_en_vivo_y_recargada(entorno, entrar(entorno), MIXTA)
    assert [m.get("metadata", {}).get("title") for m in chat[1:]] == [None, "Fuentes: [F1]", "Consultas: [T1]"]


def test_conversacion_recargada_identica_con_limitacion(entorno):
    entorno.llm.colas["respuesta_rag"] = [rag(respuesta="Debe incluir el NIT [F1].", estado="parcial", limitacion="Los pasajes no tratan el total.")]
    chat = comparar_en_vivo_y_recargada(entorno, entrar(entorno), "¿Qué datos debe traer una factura?")
    assert "Limitación: Los pasajes no tratan el total." in chat[1]["content"] and ap.ESTADOS["PARCIAL"] in chat[1]["content"]


def test_conversacion_recargada_identica_con_error_tecnico_y_su_detalle(entorno):
    entorno.sistema.mcp_estado = MCPFalso(error=si.ErrorTecnico("mcp"))
    chat = comparar_en_vivo_y_recargada(entorno, entrar(entorno), "¿Cómo va DOC-1001?")
    assert chat[-1]["content"].endswith("Detalle: " + si.DETALLE_TECNICO["mcp"])


def test_conversacion_recargada_identica_con_limite_de_consultas(entorno):
    chat = comparar_en_vivo_y_recargada(entorno, entrar(entorno), "¿Cómo van DOC-1003, SOL-1002 y SOL-1001?")
    assert "Limitación: " + si.MENSAJES["LIMITE_CONSULTAS"] in chat[1]["content"] and chat[-1]["metadata"]["title"] == "Consultas: [T1] [T2]"


def test_detalle_solo_se_muestra_en_errores_tecnicos():
    fila = {"rol": "asistente", "contenido": "texto", "estado": "RESPONDIDA", "detalle_error": "interno", "limitacion": ""}
    assert "Detalle" not in ap.mensajes_de_fila(fila)[0]["content"]
    assert "Detalle: interno" in ap.mensajes_de_fila({**fila, "estado": "ERROR_TECNICO"})[0]["content"]


def test_datos_del_registro_en_orden_fijo_sin_importar_el_orden_guardado():
    base = {"etiqueta": "T1", "operacion": "consultar_estado_solicitud", "citada": True}
    uno = {**base, "resultado": {"codigo_solicitud": "DOC-1001", "fuente": "r", "encontrado": True, "registro": {"tipo": "factura", "monto": "1", "estado": "x"}}}
    dos = {**base, "resultado": {"codigo_solicitud": "DOC-1001", "fuente": "r", "encontrado": True, "registro": {"monto": "1", "estado": "x", "tipo": "factura"}}}
    assert ap.bloque_herramientas([uno]) == ap.bloque_herramientas([dos])
    assert ap.bloque_herramientas([uno]).index("Estado: x") < ap.bloque_herramientas([uno]).index("Monto: 1")


INFORME = "¿Qué datos debe traer una factura? Haz un informe"


def proponer_en_vivo(e, sesion=None):
    sesion = sesion or entrar(e)
    return sesion, responder(e, sesion, INFORME)


def test_propuesta_sin_decidir_se_vuelve_a_ofrecer_al_recargar(entorno):
    sesion, en_vivo = proponer_en_vivo(entorno)
    recargada = entorno.interfaz.seleccionar(sesion, en_vivo["conversacion"])
    assert recargada["chat"] == en_vivo["chat"] and recargada["propuesta"] == en_vivo["propuesta"]
    assert recargada["informe"]["visible"] and recargada["aprobar"]["interactive"] and recargada["rechazar"]["interactive"]
    assert recargada["informe_contenido"] == en_vivo["informe_contenido"] and recargada["informe_destino"] == en_vivo["informe_destino"]
    assert recargada["indicador"] == "Conversación cargada. Hay una propuesta de informe que espera tu aprobación."
    salida = asyncio.run(entorno.interfaz.aprobar(sesion, recargada["propuesta"], recargada["chat"]))
    assert salida["archivo"]["visible"] and len(entorno.escritor.escrituras) == 1


@pytest.mark.parametrize("decision, nota", [("aprobar", "aprobado y escrito"), ("rechazar", "rechazado; no se escribió ningún archivo")])
def test_decision_registrada_se_muestra_igual_en_vivo_y_al_recargar(entorno, decision, nota):
    sesion, en_vivo = proponer_en_vivo(entorno)
    salida = asyncio.run(getattr(entorno.interfaz, decision)(sesion, en_vivo["propuesta"], en_vivo["chat"]))
    assert salida["chat"][-1] == ap.mensaje_decision(en_vivo["propuesta"]["destino"], {"decision": "aprobada" if decision == "aprobar" else "rechazada",
                                                                                        "resultado": "ejecutada" if decision == "aprobar" else None})
    assert nota in salida["chat"][-1]["content"]
    recargada = entorno.interfaz.seleccionar(sesion, en_vivo["conversacion"])
    assert recargada["chat"] == salida["chat"] and recargada["propuesta"] is None and not recargada["informe"]["visible"]
    repetida = asyncio.run(getattr(entorno.interfaz, decision)(sesion, en_vivo["propuesta"], salida["chat"]))
    assert repetida["chat"] == salida["chat"] and len(entorno.escritor.escrituras) == (1 if decision == "aprobar" else 0)


def test_escritura_fallida_se_muestra_al_recargar(entorno):
    entorno.sistema.escritor = EscritorDisco(error=si.ErrorTecnico("mcp_archivos"))
    sesion, en_vivo = proponer_en_vivo(entorno)
    salida = asyncio.run(entorno.interfaz.aprobar(sesion, en_vivo["propuesta"], en_vivo["chat"]))
    recargada = entorno.interfaz.seleccionar(sesion, en_vivo["conversacion"])
    assert "la escritura falló y no se reintenta" in recargada["chat"][-1]["content"] and recargada["chat"] == salida["chat"]


def test_propuesta_alterada_en_la_base_no_se_ofrece(entorno):
    sesion, en_vivo = proponer_en_vivo(entorno)
    fila = next(m for m in entorno.base.tablas["mensajes"] if m.get("propuesta_informe"))
    fila["propuesta_informe"] = {**fila["propuesta_informe"], "contenido": "contenido cambiado"}
    recargada = entorno.interfaz.seleccionar(sesion, en_vivo["conversacion"])
    assert recargada["propuesta"] is None and not recargada["informe"]["visible"]


def test_con_dos_propuestas_pendientes_se_ofrece_la_mas_reciente_y_luego_la_otra(entorno):
    sesion, primera = proponer_en_vivo(entorno)
    segunda = responder(entorno, sesion, INFORME, primera["conversacion"], primera["chat"])
    recargada = entorno.interfaz.seleccionar(sesion, primera["conversacion"])
    assert recargada["propuesta"]["mensaje_id"] == segunda["propuesta"]["mensaje_id"]
    asyncio.run(entorno.interfaz.rechazar(sesion, recargada["propuesta"], recargada["chat"]))
    assert entorno.interfaz.seleccionar(sesion, primera["conversacion"])["propuesta"]["mensaje_id"] == primera["propuesta"]["mensaje_id"]


def test_la_sesion_renovada_se_devuelve_tambien_en_los_caminos_de_error(entorno):
    sesion, en_vivo = proponer_en_vivo(entorno)
    asyncio.run(entorno.interfaz.rechazar(sesion, en_vivo["propuesta"], en_vivo["chat"]))
    entorno.reloj.ahora += 3600 - 30
    repetida = asyncio.run(entorno.interfaz.aprobar(sesion, en_vivo["propuesta"], en_vivo["chat"]))
    assert repetida["sesion"]["access_token"] != sesion["access_token"]
    entorno.reloj.ahora += 3600 - 30
    ajena = entorno.almacen.crear_conversacion("token-b", "De B")["id"]
    denegada = entorno.interfaz.seleccionar(repetida["sesion"], ajena)
    assert denegada["sesion"]["access_token"] not in (sesion["access_token"], repetida["sesion"]["access_token"])
    assert denegada["indicador"] == ap.ESTADOS["ACCESO_DENEGADO"]


def en_vivo(e, sesion, texto, conversacion=None, chat=None):
    async def recorrer():
        return [parcial async for parcial in e.interfaz.responder_en_vivo(sesion, conversacion, texto, chat or [])]
    return asyncio.run(recorrer())


def test_en_vivo_muestra_la_espera_de_cupo_y_reactiva_los_controles(entorno):
    original = entorno.sistema.atender

    async def con_espera(texto, conversacion, token, al_esperar=None):
        al_esperar(30.0)
        await asyncio.sleep(0.05)
        return await original(texto, conversacion, token, al_esperar=al_esperar)

    entorno.sistema.atender = con_espera
    parciales = en_vivo(entorno, entrar(entorno), "¿Qué datos debe traer una factura?")
    assert parciales[0] == {"indicador": "Esperando cupo del proveedor del modelo…"}
    final = parciales[-1]
    assert final["indicador"] == ap.ESTADOS["RESPONDIDA"] and all(final[n]["interactive"] for n in ("entrada", "enviar", "nueva", "salir", "lista"))
    assert final["lista"]["choices"] and final["lista"]["value"] == final["conversacion"]


def test_en_vivo_reactiva_los_controles_aunque_falle(entorno):
    async def falla(*argumentos, **opciones):
        raise RuntimeError("inesperado")

    entorno.sistema.atender = falla
    final = en_vivo(entorno, entrar(entorno), "¿Qué datos debe traer una factura?")[-1]
    assert final["indicador"] == ap.ESTADOS["ERROR_TECNICO"] and all(final[n]["interactive"] for n in ("entrada", "enviar", "nueva", "salir", "lista"))


def test_lista_muestra_veinte_y_ver_mas_agrega_otras_veinte(entorno):
    for numero in range(45):
        entorno.almacen.crear_conversacion("token-a", f"Conversación {numero:02d}")
    salida = entorno.interfaz.entrar("a@prueba.local", CLAVES["a@prueba.local"])
    assert len(salida["lista"]["choices"]) == 20 and salida["ver_mas"]["visible"] and salida["lista"]["interactive"]
    mas = entorno.interfaz.ver_mas(salida["sesion"], salida["limite"], None)
    assert len(mas["lista"]["choices"]) == 40 and mas["ver_mas"]["visible"] and mas["limite"] == 40
    todas = entorno.interfaz.ver_mas(mas["sesion"], mas["limite"], None)
    assert len(todas["lista"]["choices"]) == 45 and not todas["ver_mas"]["visible"]
    pocas = entorno.interfaz.entrar("b@prueba.local", CLAVES["b@prueba.local"])
    assert pocas["lista"]["choices"] == [] and not pocas["ver_mas"]["visible"]


def test_indicador_unico_al_recargar(entorno):
    sesion, en_vivo_propuesta = proponer_en_vivo(entorno)
    pendiente = entorno.interfaz.seleccionar(sesion, en_vivo_propuesta["conversacion"])["indicador"]
    assert pendiente == "Conversación cargada. Hay una propuesta de informe que espera tu aprobación."
    asyncio.run(entorno.interfaz.rechazar(sesion, en_vivo_propuesta["propuesta"], en_vivo_propuesta["chat"]))
    decidida = entorno.interfaz.seleccionar(sesion, en_vivo_propuesta["conversacion"])["indicador"]
    assert decidida == "Conversación cargada. La propuesta de informe ya tiene una decisión registrada."
    for texto in (pendiente, decidida):
        assert texto.count("informe") == 1 and texto.count("Conversación cargada") == 1


@pytest.mark.parametrize("sesion, valida", [(None, False), ({}, False), ({"access_token": "x"}, False), ("token", False),
                                            ({"access_token": "x", "refresh_token": "y", "expira_en": 1.0}, True)])
def test_validador_exige_sesion(sesion, valida):
    if valida:
        assert ap.exigir_sesion(sesion, "otro") == [gr.validate(True, ""), gr.validate(True, "")]
        assert ap.exigir_sesion(sesion) == gr.validate(True, "")
    else:
        with pytest.raises(gr.Error):
            ap.exigir_sesion(sesion, "otro")
