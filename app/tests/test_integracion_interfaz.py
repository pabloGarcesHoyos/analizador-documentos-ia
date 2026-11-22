import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

import almacenamiento as al
import app as ap
import sistema as si
from test_integracion_supabase import _entorno

pytestmark = pytest.mark.integracion


class SistemaSinModelo:
    def __init__(self, almacen):
        self.almacen = almacen

    async def atender(self, texto, conversacion_id, token):
        _, guardado = await asyncio.to_thread(self.almacen.guardar_turno, token, conversacion_id, texto, "Respuesta de prueba sin modelo.", "RESPONDIDA")
        return si.ResultadoAtencion("RESPONDIDA", "Respuesta de prueba sin modelo.", conversacion_id, mensaje_id=guardado["id"], persistido=True)


@pytest.fixture(scope="module")
def entorno():
    return _entorno()


@pytest.fixture(scope="module")
def interfaz(entorno):
    configuracion = al.ConfiguracionSupabase.desde_entorno(entorno)
    almacen = al.Almacenamiento(configuracion)
    return ap.Interfaz(al.Autenticacion(configuracion), almacen, SistemaSinModelo(almacen))


def test_dos_sesiones_simultaneas_no_comparten_conversaciones(entorno, interfaz):
    with ThreadPoolExecutor(2) as hilos:
        entrada_a, entrada_b = hilos.map(lambda par: interfaz.entrar(entorno[par[0]], entorno[par[1]]),
                                         [("PRUEBA_A_EMAIL", "PRUEBA_A_PASSWORD"), ("PRUEBA_B_EMAIL", "PRUEBA_B_PASSWORD")])
    sesion_a, sesion_b = entrada_a["sesion"], entrada_b["sesion"]
    assert sesion_a and sesion_b and sesion_a["usuario_id"] != sesion_b["usuario_id"]

    async def ambas():
        return await asyncio.gather(interfaz.responder(sesion_a, None, "Pregunta de integración de A", []),
                                    interfaz.responder(sesion_b, None, "Pregunta de integración de B", []))

    salida_a, salida_b = asyncio.run(ambas())
    propia_a, propia_b = salida_a["conversacion"], salida_b["conversacion"]
    ids_b = [valor for _, valor in salida_b["lista"]["choices"]]
    assert propia_b in ids_b and propia_a not in ids_b
    assert propia_a in [valor for _, valor in salida_a["lista"]["choices"]]
    intento = interfaz.seleccionar(sesion_b, propia_a)
    assert intento["chat"] == [] and intento["conversacion"] is None and intento["indicador"] == ap.ESTADOS["ACCESO_DENEGADO"]
    propia = interfaz.seleccionar(sesion_a, propia_a)
    assert propia["chat"][0]["content"] == "Pregunta de integración de A"
    with pytest.raises(al.AccesoDenegado):
        interfaz.almacen.cargar_mensajes(sesion_b["access_token"], propia_a)


def test_renovacion_real_del_token(entorno, interfaz):
    sesion = interfaz.entrar(entorno["PRUEBA_A_EMAIL"], entorno["PRUEBA_A_PASSWORD"])["sesion"]
    vencida = {**sesion, "expira_en": 0}
    renovada = interfaz.seleccionar(vencida, interfaz.almacen.listar_conversaciones(sesion["access_token"])[0]["id"])["sesion"]
    assert renovada["access_token"] != sesion["access_token"] and renovada["refresh_token"] != sesion["refresh_token"]
    assert interfaz.almacen.usuario(renovada["access_token"]) == sesion["usuario_id"]
    interfaz.salir(renovada)
