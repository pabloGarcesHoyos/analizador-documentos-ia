import hashlib
import math
import uuid
from pathlib import Path

import pytest
from dotenv import dotenv_values
from postgrest.exceptions import APIError

import almacenamiento as al

pytestmark = pytest.mark.integracion

CARPETA_APP = Path(__file__).resolve().parents[1]
MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
HUELLA = hashlib.sha256(b"informe de prueba").hexdigest()
VECTOR = [round(1 / math.sqrt(384), 6)] * 384
FUNCION = "analizador_buscar_fragmentos_autorizado"


def _entorno():
    entorno = {}
    for nombre in (".env", ".env.pruebas"):
        ruta = CARPETA_APP / nombre
        if not ruta.exists():
            pytest.skip(f"Falta app/{nombre}")
        entorno.update({k: v for k, v in dotenv_values(ruta).items() if v})
    requeridas = ["SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "PRUEBA_A_EMAIL", "PRUEBA_A_PASSWORD", "PRUEBA_B_EMAIL", "PRUEBA_B_PASSWORD"]
    faltantes = [n for n in requeridas if n not in entorno]
    if faltantes:
        pytest.skip("Faltan variables: " + ", ".join(faltantes))
    return entorno


@pytest.fixture(scope="module")
def entorno():
    return _entorno()


@pytest.fixture(scope="module")
def configuracion(entorno):
    return al.ConfiguracionSupabase.desde_entorno(entorno)


def _iniciar_sesion(configuracion, correo, clave):
    from supabase import ClientOptions, create_client
    cliente = create_client(configuracion.url, configuracion.clave_publicable,
                            options=ClientOptions(persist_session=False, auto_refresh_token=False))
    sesion = cliente.auth.sign_in_with_password({"email": correo, "password": clave})
    return sesion.session.access_token, str(sesion.user.id)


@pytest.fixture(scope="module")
def sesiones(entorno, configuracion):
    a = _iniciar_sesion(configuracion, entorno["PRUEBA_A_EMAIL"], entorno["PRUEBA_A_PASSWORD"])
    b = _iniciar_sesion(configuracion, entorno["PRUEBA_B_EMAIL"], entorno["PRUEBA_B_PASSWORD"])
    assert a[1] != b[1], "Los usuarios A y B deben ser distintos"
    return {"a": a, "b": b}


@pytest.fixture(scope="module")
def almacen(configuracion):
    return al.Almacenamiento(configuracion)


def _directo(configuracion, token):
    return al.crear_cliente(configuracion, token)


def _titulo():
    return f"prueba-integracion-{uuid.uuid4().hex[:8]}"


def test_cada_usuario_es_quien_dice_su_token(almacen, sesiones):
    assert almacen.usuario(sesiones["a"][0]) == sesiones["a"][1]
    assert almacen.usuario(sesiones["b"][0]) == sesiones["b"][1]
    with pytest.raises(al.SesionInvalida):
        almacen.usuario(sesiones["a"][0][:-4] + "abcd")


def test_turno_completo_y_orden(almacen, sesiones):
    token = sesiones["a"][0]
    conversacion = almacen.crear_conversacion(token, _titulo())
    fuentes = [{"etiqueta": "F1", "chunk_id": "politicas_facturacion:2.0-2026-10:parrafos:001"}]
    almacen.guardar_turno(token, conversacion["id"], "pregunta 1", "respuesta 1", "RESPONDER", fuentes=fuentes)
    almacen.guardar_turno(token, conversacion["id"], "pregunta 2", "respuesta 2", "ACLARAR")
    mensajes = almacen.cargar_mensajes(token, conversacion["id"])
    assert [m["contenido"] for m in mensajes] == ["pregunta 1", "respuesta 1", "pregunta 2", "respuesta 2"]
    assert mensajes[1]["fuentes"] == fuentes and mensajes[3]["estado"] == "ACLARAR"


def test_dos_conversaciones_de_la_misma_persona(almacen, sesiones):
    token = sesiones["a"][0]
    primera = almacen.crear_conversacion(token, _titulo())
    segunda = almacen.crear_conversacion(token, _titulo())
    ids = {c["id"] for c in almacen.listar_conversaciones(token)}
    assert {primera["id"], segunda["id"]} <= ids


def test_b_no_lee_ni_lista_la_conversacion_de_a(almacen, configuracion, sesiones):
    token_a, token_b = sesiones["a"][0], sesiones["b"][0]
    conversacion = almacen.crear_conversacion(token_a, _titulo())
    almacen.guardar_turno(token_a, conversacion["id"], "privada", "respuesta privada", "RESPONDER")
    assert conversacion["id"] not in {c["id"] for c in almacen.listar_conversaciones(token_b)}
    with pytest.raises(al.AccesoDenegado):
        almacen.cargar_mensajes(token_b, conversacion["id"])
    directo = _directo(configuracion, token_b)
    assert directo.table("conversaciones").select("id").eq("id", conversacion["id"]).execute().data == []
    assert directo.table("mensajes").select("id").eq("conversacion_id", conversacion["id"]).execute().data == []


def test_b_no_inserta_en_la_conversacion_de_a(almacen, configuracion, sesiones):
    token_a, token_b = sesiones["a"][0], sesiones["b"][0]
    conversacion = almacen.crear_conversacion(token_a, _titulo())
    with pytest.raises(al.AccesoDenegado):
        almacen.guardar_turno(token_b, conversacion["id"], "intruso", "intruso", "RESPONDER")
    directo = _directo(configuracion, token_b)
    for fila in ({"conversacion_id": conversacion["id"], "rol": "usuario", "contenido": "intruso"},
                 {"conversacion_id": conversacion["id"], "usuario_id": sesiones["a"][1], "rol": "usuario", "contenido": "intruso"}):
        with pytest.raises(APIError) as error:
            directo.table("mensajes").insert(fila).execute()
        assert error.value.code in {"42501", "23503"}
    assert almacen.cargar_mensajes(token_a, conversacion["id"]) == []


def test_decision_de_informe_unica(almacen, sesiones):
    token_a, token_b = sesiones["a"][0], sesiones["b"][0]
    conversacion = almacen.crear_conversacion(token_a, _titulo())
    _, respuesta = almacen.guardar_turno(token_a, conversacion["id"], "pide informe", "respuesta con fuentes", "RESPONDER")
    accion = almacen.registrar_decision_informe(token_a, conversacion["id"], respuesta["id"], "aprobada", "informe_prueba.md", HUELLA)
    with pytest.raises(al.AccionYaRegistrada):
        almacen.registrar_decision_informe(token_a, conversacion["id"], respuesta["id"], "aprobada", "informe_prueba.md", HUELLA)
    with pytest.raises(al.AccesoDenegado):
        almacen.registrar_decision_informe(token_b, conversacion["id"], respuesta["id"], "aprobada", "informe_prueba.md", HUELLA)
    with pytest.raises(al.AccionYaRegistrada):
        almacen.registrar_resultado_informe(token_b, accion["id"], "ejecutada")
    assert almacen.registrar_resultado_informe(token_a, accion["id"], "ejecutada")["resultado"] == "ejecutada"
    with pytest.raises(al.AccionYaRegistrada):
        almacen.registrar_resultado_informe(token_a, accion["id"], "fallida")


def test_lector_autorizado_busca_en_el_corpus_y_el_otro_no(entorno, configuracion, sesiones):
    for nombre in ("CORPUS_ID", "CORPUS_PROPIETARIO_ID"):
        if nombre not in entorno:
            pytest.skip(f"Falta {nombre} en app/.env")
    parametros = {"query_embedding": VECTOR, "p_propietario_id": entorno["CORPUS_PROPIETARIO_ID"], "p_corpus_id": entorno["CORPUS_ID"],
                  "p_modelo": MODELO, "p_revision": REVISION, "match_count": 10}
    lector = _directo(configuracion, sesiones["a"][0]).rpc(FUNCION, parametros).execute().data
    otro = _directo(configuracion, sesiones["b"][0]).rpc(FUNCION, parametros).execute().data
    assert len(lector) == 10
    assert otro == []
    filas = (_directo(configuracion, sesiones["a"][0]).table("analizador_fragmentos").select("chunk_id")
             .eq("owner_id", entorno["CORPUS_PROPIETARIO_ID"]).eq("corpus_id", entorno["CORPUS_ID"]).execute().data)
    assert len(filas) == 20


def test_anonimo_sin_acceso(configuracion):
    anonimo = al.crear_cliente(configuracion, configuracion.clave_publicable)
    for tabla in ("conversaciones", "mensajes", "acciones_informe", "lectores_corpus", "analizador_fragmentos"):
        try:
            datos = anonimo.table(tabla).select("*").limit(1).execute().data
        except APIError as error:
            assert error.code in {"42501", "PGRST301"}
        else:
            assert datos == []
