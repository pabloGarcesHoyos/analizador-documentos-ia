import json
import socket
import uuid

import httpx
import pytest

import app as ap
from test_app import crear_entorno


@pytest.fixture
def entorno(tmp_path):
    return crear_entorno(tmp_path)


def puerto_libre() -> int:
    with socket.socket() as conexion:
        conexion.bind(("127.0.0.1", 0))
        return conexion.getsockname()[1]


@pytest.fixture
def servidor(entorno):
    puerto = puerto_libre()
    demo = ap.preparar(ap.construir(entorno.interfaz))
    demo.launch(**{**ap.opciones_lanzamiento("127.0.0.1", puerto), "prevent_thread_lock": True, "quiet": True})
    try:
        yield demo, f"http://127.0.0.1:{puerto}"
    finally:
        demo.close()


def unirse(url: str, indice: int, datos: list, sesion: str) -> httpx.Response:
    return httpx.post(f"{url}/gradio_api/queue/join", json={"data": datos, "fn_index": indice, "session_hash": sesion, "event_data": None}, timeout=20)


def resultado_de_la_cola(url: str, sesion: str) -> dict:
    with httpx.stream("GET", f"{url}/gradio_api/queue/data", params={"session_hash": sesion}, timeout=20) as respuesta:
        for linea in respuesta.iter_lines():
            if linea.startswith("data:"):
                mensaje = json.loads(linea[5:])
                if mensaje.get("msg") == "process_completed":
                    return mensaje
    raise AssertionError("La cola no terminó el evento.")


@pytest.mark.parametrize("metodo, ruta", [
    ("GET", "/gradio_api/info"), ("GET", "/gradio_api/info/"), ("GET", "/gradio_api/openapi.json"),
    ("POST", "/gradio_api/call/entrar"), ("POST", "/gradio_api/call/v2/entrar"), ("POST", "/gradio_api/run/predict"),
    ("POST", "/gradio_api/api/predict"), ("POST", "/gradio_api/upload"), ("GET", "/gradio_api/upload_progress"), ("GET", "/monitoring"),
])
def test_rutas_de_api_directa_responden_404_controlado(servidor, metodo, ruta):
    _, url = servidor
    respuesta = httpx.request(metodo, url + ruta, json={"data": [], "fn_index": 0}, timeout=20)
    assert respuesta.status_code == 404 and respuesta.json() == {"detail": "No disponible."}


def test_la_pagina_sigue_disponible_con_etiquetas_propias(servidor):
    _, url = servidor
    pagina = httpx.get(url + "/", timeout=20)
    assert pagina.status_code == 200 and "Conversación con el analizador" in pagina.text


def test_todos_los_eventos_privados_sin_progreso_de_gradio(servidor):
    demo, _ = servidor
    funciones = list(demo.fns.values())
    assert funciones and all(f.api_visibility == "private" and f.show_progress == "hidden" and f.queue for f in funciones)
    sin_validador = [f for f in funciones if f.validator is None]
    assert len(sin_validador) == 2 and all(f.fn.__qualname__.startswith("_envolver") for f in sin_validador)


def test_cola_sin_sesion_valida_termina_en_error_controlado(servidor):
    demo, url = servidor
    protegidas = [(indice, f) for indice, f in demo.fns.items() if f.validator is not None]
    assert len(protegidas) >= 8
    for indice, funcion in protegidas:
        respuesta = unirse(url, indice, [None] * len(funcion.inputs), uuid.uuid4().hex[:11])
        assert respuesta.status_code == 400, (indice, respuesta.status_code)
        assert "Sesión no válida" in respuesta.json()["detail"]


def test_cola_con_uuid_ajeno_y_sin_sesion_no_devuelve_datos(servidor, entorno):
    demo, url = servidor
    ajena = entorno.almacen.crear_conversacion("token-a", "Privada de A")["id"]
    entorno.almacen.guardar_turno("token-a", ajena, "secreto de A", "respuesta privada de A", "RESPONDIDA")
    indice = next(i for i, f in demo.fns.items() if any(getattr(b, "label", None) == "Conversaciones recientes" for b in f.inputs))
    respuesta = unirse(url, indice, [None, ajena], uuid.uuid4().hex[:11])
    assert respuesta.status_code == 400 and "secreto de A" not in respuesta.text and "respuesta privada" not in respuesta.text


def test_inicio_de_sesion_por_la_cola_solo_devuelve_el_aviso(servidor):
    demo, url = servidor
    indice = next(i for i, f in demo.fns.items() if f.validator is None)
    sesion = uuid.uuid4().hex[:11]
    respuesta = unirse(url, indice, ["a@prueba.local", "incorrecta"], sesion)
    assert respuesta.status_code == 200
    final = json.dumps(resultado_de_la_cola(url, sesion), ensure_ascii=False)
    assert "No se pudo iniciar sesión" in final and "access_token" not in final and "token-a" not in final


def test_cola_con_sesion_valida_si_ejecuta_los_eventos(servidor):
    demo, url = servidor
    sesion = uuid.uuid4().hex[:11]
    inicio = next(i for i, f in demo.fns.items() if f.validator is None)
    assert unirse(url, inicio, ["a@prueba.local", "clave-a-secreta"], sesion).status_code == 200
    resultado_de_la_cola(url, sesion)
    nueva = next(i for i, f in demo.fns.items() if f.validator is not None and len(f.inputs) == 1 and len(f.outputs) == 8)
    respuesta = unirse(url, nueva, [None], sesion)
    assert respuesta.status_code == 200, respuesta.text
    final = resultado_de_la_cola(url, sesion)
    assert final["success"] is True and "se guardará al enviar la primera pregunta" in json.dumps(final, ensure_ascii=False)
