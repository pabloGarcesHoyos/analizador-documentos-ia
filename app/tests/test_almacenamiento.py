import hashlib
import math
import uuid

import pytest
from postgrest.exceptions import APIError

import almacenamiento as al
from supabase_falso import BaseFalsa

USUARIO_A = str(uuid.uuid4())
USUARIO_B = str(uuid.uuid4())
HUELLA = hashlib.sha256(b"informe").hexdigest()


@pytest.fixture
def base():
    return BaseFalsa({"token-a": USUARIO_A, "token-b": USUARIO_B})


@pytest.fixture
def almacen(base):
    configuracion = al.ConfiguracionSupabase("https://proyecto.supabase.co", "sb_publishable_ejemplo")
    return al.Almacenamiento(configuracion, fabrica=base.fabrica)


def turno(almacen, token, conversacion_id, numero=1, fuentes=None):
    return almacen.guardar_turno(token, conversacion_id, f"pregunta {numero}", f"respuesta {numero}", "RESPONDER",
                                 fuentes=fuentes or [], herramientas=[], traza={"paso": numero})


def test_configuracion_nombra_las_variables_faltantes():
    with pytest.raises(al.ConfiguracionInvalida, match="SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY"):
        al.ConfiguracionSupabase.desde_entorno({})
    with pytest.raises(al.ConfiguracionInvalida, match="SUPABASE_PUBLISHABLE_KEY"):
        al.ConfiguracionSupabase.desde_entorno({"SUPABASE_URL": "https://p.supabase.co", "SUPABASE_PUBLISHABLE_KEY": "  "})


def test_configuracion_rechaza_clave_administrativa_y_url_invalida():
    with pytest.raises(al.ConfiguracionInvalida, match="clave publicable"):
        al.ConfiguracionSupabase("https://p.supabase.co", "sb_secret_algo")
    with pytest.raises(al.ConfiguracionInvalida, match="SUPABASE_URL"):
        al.ConfiguracionSupabase("ftp://p.supabase.co", "sb_publishable_x")
    with pytest.raises(al.ConfiguracionInvalida):
        al.ConfiguracionSupabase("http://p.supabase.co", "sb_publishable_x")


def test_configuracion_acepta_proyecto_y_entorno_local():
    assert al.ConfiguracionSupabase.desde_entorno(
        {"SUPABASE_URL": "https://p.supabase.co/", "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_x"}).url == "https://p.supabase.co"
    assert al.ConfiguracionSupabase("http://127.0.0.1:54321", "sb_publishable_x").url == "http://127.0.0.1:54321"


def test_crear_cliente_usa_el_token_del_usuario():
    configuracion = al.ConfiguracionSupabase("https://p.supabase.co", "sb_publishable_x")
    primero = al.crear_cliente(configuracion, "token-uno")
    segundo = al.crear_cliente(configuracion, "token-dos")
    assert primero is not segundo
    assert primero.options.headers["Authorization"] == "Bearer token-uno"
    assert segundo.options.headers["Authorization"] == "Bearer token-dos"
    assert primero.postgrest.session.headers["Authorization"] == "Bearer token-uno"


def test_cada_operacion_crea_su_cliente_y_valida_la_identidad(base, almacen):
    conversacion = almacen.crear_conversacion("token-a", "Primera")
    almacen.listar_conversaciones("token-b")
    almacen.cargar_mensajes("token-a", conversacion["id"])
    assert base.tokens_usados == ["token-a", "token-b", "token-a"]
    assert base.consultas_get_user == 3
    assert not any(isinstance(v, al.Almacenamiento) or hasattr(v, "table") for v in vars(almacen).values())


def test_sesion_invalida_o_vacia(base, almacen):
    with pytest.raises(al.SesionInvalida):
        almacen.listar_conversaciones("token-falso")
    with pytest.raises(al.SesionInvalida):
        almacen.listar_conversaciones("   ")
    assert base.tokens_usados == ["token-falso"]


def test_cada_usuario_lista_solo_sus_conversaciones(almacen):
    a = almacen.crear_conversacion("token-a", "De A")
    b = almacen.crear_conversacion("token-b", "De B")
    assert [c["id"] for c in almacen.listar_conversaciones("token-a")] == [a["id"]]
    assert [c["id"] for c in almacen.listar_conversaciones("token-b")] == [b["id"]]


def test_conversacion_nueva_no_borra_la_anterior(almacen):
    primera = almacen.crear_conversacion("token-a", "Primera")
    turno(almacen, "token-a", primera["id"])
    segunda = almacen.crear_conversacion("token-a", "Segunda")
    ids = {c["id"] for c in almacen.listar_conversaciones("token-a")}
    assert ids == {primera["id"], segunda["id"]}
    assert len(almacen.cargar_mensajes("token-a", primera["id"])) == 2


def test_otro_usuario_no_lee_ni_escribe_conociendo_el_uuid(base, almacen):
    conversacion = almacen.crear_conversacion("token-a", "Privada")
    turno(almacen, "token-a", conversacion["id"])
    with pytest.raises(al.AccesoDenegado):
        almacen.cargar_mensajes("token-b", conversacion["id"])
    with pytest.raises(al.AccesoDenegado):
        turno(almacen, "token-b", conversacion["id"], numero=2)
    with pytest.raises(al.AccesoDenegado):
        almacen.ventana_contexto("token-b", conversacion["id"])
    assert len(base.tablas["mensajes"]) == 2


def test_turno_guarda_ambos_mensajes_en_orden_con_fuentes(almacen):
    conversacion = almacen.crear_conversacion("token-a", "Fuentes")
    fuentes = [{"etiqueta": "F1", "chunk_id": "politicas:2.0:parrafos:001", "source": "politicas_facturacion.md"}]
    pregunta, respuesta = turno(almacen, "token-a", conversacion["id"], fuentes=fuentes)
    assert pregunta["rol"] == "usuario" and respuesta["rol"] == "asistente"
    assert pregunta["id"] < respuesta["id"]
    assert pregunta["fuentes"] == [] and respuesta["fuentes"] == fuentes
    mensajes = almacen.cargar_mensajes("token-a", conversacion["id"])
    assert [m["rol"] for m in mensajes] == ["usuario", "asistente"]
    assert mensajes[1]["fuentes"] == fuentes and mensajes[1]["estado"] == "RESPONDER"


def test_ventana_de_contexto_trae_los_ultimos_cuatro_turnos_en_orden(almacen):
    conversacion = almacen.crear_conversacion("token-a", "Larga")
    for numero in range(1, 7):
        turno(almacen, "token-a", conversacion["id"], numero=numero)
    ventana = almacen.ventana_contexto("token-a", conversacion["id"])
    assert len(ventana) == 8
    assert ventana[0]["contenido"] == "pregunta 3" and ventana[-1]["contenido"] == "respuesta 6"
    assert [m["id"] for m in ventana] == sorted(m["id"] for m in ventana)
    assert len(almacen.cargar_mensajes("token-a", conversacion["id"])) == 12


@pytest.mark.parametrize("campo, valor", [
    ("conversacion_id", "no-es-uuid"),
    ("pregunta", "   "),
    ("respuesta", "x" * (al.MAX_CONTENIDO + 1)),
    ("estado", ""),
    ("fuentes", "F1"),
    ("fuentes", [{"puntaje": math.nan}]),
    ("traza", ["no", "es", "objeto"]),
])
def test_guardar_turno_valida_los_datos_antes_de_consultar(base, almacen, campo, valor):
    conversacion = almacen.crear_conversacion("token-a", "Validaciones")
    datos = {"conversacion_id": conversacion["id"], "pregunta": "p", "respuesta": "r", "estado": "RESPONDER",
             "fuentes": [], "herramientas": [], "traza": None}
    datos[campo] = valor
    antes = len(base.tokens_usados)
    with pytest.raises(al.DatosInvalidos):
        almacen.guardar_turno("token-a", **datos)
    assert len(base.tokens_usados) == antes
    assert base.tablas["mensajes"] == []


def test_titulo_invalido(almacen):
    with pytest.raises(al.DatosInvalidos):
        almacen.crear_conversacion("token-a", " ")
    with pytest.raises(al.DatosInvalidos):
        almacen.crear_conversacion("token-a", "t" * (al.MAX_TITULO + 1))


def test_decision_de_informe_se_registra_una_sola_vez(almacen):
    conversacion = almacen.crear_conversacion("token-a", "Informe")
    _, respuesta = turno(almacen, "token-a", conversacion["id"])
    accion = almacen.registrar_decision_informe("token-a", conversacion["id"], respuesta["id"], "aprobada", "informe_1.md", HUELLA)
    assert accion["decision"] == "aprobada" and accion["resultado"] is None
    with pytest.raises(al.AccionYaRegistrada):
        almacen.registrar_decision_informe("token-a", conversacion["id"], respuesta["id"], "aprobada", "informe_1.md", HUELLA)
    ejecutada = almacen.registrar_resultado_informe("token-a", accion["id"], "ejecutada")
    assert ejecutada["resultado"] == "ejecutada"
    with pytest.raises(al.AccionYaRegistrada):
        almacen.registrar_resultado_informe("token-a", accion["id"], "fallida")


def test_rechazo_no_admite_resultado(almacen):
    conversacion = almacen.crear_conversacion("token-a", "Rechazo")
    _, respuesta = turno(almacen, "token-a", conversacion["id"])
    accion = almacen.registrar_decision_informe("token-a", conversacion["id"], respuesta["id"], "rechazada", "informe.md", HUELLA)
    with pytest.raises(al.AccionYaRegistrada):
        almacen.registrar_resultado_informe("token-a", accion["id"], "ejecutada")


def test_decision_exige_mensaje_del_asistente_de_esa_conversacion(almacen):
    primera = almacen.crear_conversacion("token-a", "Una")
    segunda = almacen.crear_conversacion("token-a", "Otra")
    pregunta, respuesta = turno(almacen, "token-a", primera["id"])
    with pytest.raises(al.AccesoDenegado):
        almacen.registrar_decision_informe("token-a", primera["id"], pregunta["id"], "aprobada", "informe.md", HUELLA)
    with pytest.raises(al.AccesoDenegado):
        almacen.registrar_decision_informe("token-a", segunda["id"], respuesta["id"], "aprobada", "informe.md", HUELLA)


def test_otro_usuario_no_registra_decisiones_ajenas(almacen):
    conversacion = almacen.crear_conversacion("token-a", "Ajena")
    _, respuesta = turno(almacen, "token-a", conversacion["id"])
    with pytest.raises(al.AccesoDenegado):
        almacen.registrar_decision_informe("token-b", conversacion["id"], respuesta["id"], "aprobada", "informe.md", HUELLA)
    accion = almacen.registrar_decision_informe("token-a", conversacion["id"], respuesta["id"], "aprobada", "informe.md", HUELLA)
    with pytest.raises(al.AccionYaRegistrada):
        almacen.registrar_resultado_informe("token-b", accion["id"], "ejecutada")


@pytest.mark.parametrize("argumentos", [
    {"mensaje_id": 0},
    {"mensaje_id": True},
    {"decision": "aprobar"},
    {"destino": ""},
    {"huella_contenido": "abc"},
])
def test_decision_valida_sus_argumentos(almacen, argumentos):
    conversacion = almacen.crear_conversacion("token-a", "Args")
    _, respuesta = turno(almacen, "token-a", conversacion["id"])
    datos = {"conversacion_id": conversacion["id"], "mensaje_id": respuesta["id"], "decision": "aprobada",
             "destino": "informe.md", "huella_contenido": HUELLA, **argumentos}
    with pytest.raises(al.DatosInvalidos):
        almacen.registrar_decision_informe("token-a", **datos)


@pytest.mark.parametrize("codigo, esperado", [
    ("42501", al.AccesoDenegado),
    ("23503", al.AccesoDenegado),
    ("PGRST301", al.AccesoDenegado),
    ("PGRST303", al.SesionInvalida),
    ("XX000", al.ErrorAlmacenamiento),
])
def test_traduccion_de_errores_de_supabase(codigo, esperado):
    error = al._error_api(APIError({"code": codigo, "message": "m"}))
    assert type(error) is esperado


def test_duplicado_solo_es_accion_registrada_cuando_se_espera():
    duplicado = APIError({"code": "23505", "message": "m"})
    assert type(al._error_api(duplicado, al.AccionYaRegistrada)) is al.AccionYaRegistrada
    assert type(al._error_api(duplicado)) is al.ErrorAlmacenamiento


def test_limites_de_listado_y_ventana(almacen):
    with pytest.raises(al.DatosInvalidos):
        almacen.listar_conversaciones("token-a", limite=0)
    with pytest.raises(al.DatosInvalidos):
        almacen.ventana_contexto("token-a", str(uuid.uuid4()), turnos=0)


def test_obtener_accion_solo_del_propietario(almacen):
    conversacion = almacen.crear_conversacion("token-a", "Accion")
    _, respuesta = turno(almacen, "token-a", conversacion["id"])
    accion = almacen.registrar_decision_informe("token-a", conversacion["id"], respuesta["id"], "aprobada", "informe.md", HUELLA)
    leida = almacen.obtener_accion_informe("token-a", accion["id"])
    assert leida["decision"] == "aprobada" and leida["huella_contenido"] == HUELLA and leida["mensaje_id"] == respuesta["id"]
    with pytest.raises(al.AccesoDenegado):
        almacen.obtener_accion_informe("token-b", accion["id"])
    with pytest.raises(al.AccesoDenegado):
        almacen.obtener_accion_informe("token-a", str(uuid.uuid4()))
    with pytest.raises(al.DatosInvalidos):
        almacen.obtener_accion_informe("token-a", "no-es-uuid")
