import pytest

import almacenamiento as al
import descargar_modelos
import recuperacion as rc
from test_integracion_supabase import _entorno, _iniciar_sesion
from test_recuperacion import CASOS, CORTE2, OPCIONES, agregado

pytestmark = [pytest.mark.integracion,
              pytest.mark.skipif(bool(descargar_modelos.faltantes()), reason="Faltan los modelos: ejecuta python app/descargar_modelos.py")]


@pytest.fixture(scope="module")
def entorno():
    datos = _entorno()
    for nombre in ("CORPUS_ID", "CORPUS_PROPIETARIO_ID"):
        if nombre not in datos:
            pytest.skip(f"Falta {nombre} en app/.env")
    return datos


@pytest.fixture(scope="module")
def configuracion(entorno):
    return al.ConfiguracionSupabase.desde_entorno(entorno)


def fuente(entorno, configuracion, correo, clave):
    token, _ = _iniciar_sesion(configuracion, entorno[correo], entorno[clave])
    return rc.FuenteSupabase(al.crear_cliente(configuracion, token), entorno["CORPUS_PROPIETARIO_ID"], entorno["CORPUS_ID"])


def test_metricas_del_corte2_contra_supabase(entorno, configuracion):
    lector = fuente(entorno, configuracion, "PRUEBA_A_EMAIL", "PRUEBA_A_PASSWORD")
    recuperador = rc.Recuperador("C_DEMANDA")
    obtenidas = {c["id"]: recuperador.evaluar(c["pregunta"], lector) for c in CASOS}
    assert agregado(obtenidas) == CORTE2
    assert sum(obtenidas[c["id"]][o] == c["seleccion_corte2"][o] for c in CASOS for o in OPCIONES) >= 42


def test_usuario_sin_autorizacion_no_recupera(entorno, configuracion):
    ajeno = fuente(entorno, configuracion, "PRUEBA_B_EMAIL", "PRUEBA_B_PASSWORD")
    with pytest.raises(rc.SinAccesoCorpus):
        rc.Recuperador("B").recuperar("¿Qué datos debe traer una factura?", ajeno)
