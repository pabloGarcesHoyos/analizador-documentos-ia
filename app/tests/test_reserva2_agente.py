import re

import pytest

from casos_agente import consulta, ejecutar_caso, herramienta, preparar_contexto, registrar

pytestmark = [pytest.mark.integracion, pytest.mark.groq, pytest.mark.reserva2]

ESTADOS_REGISTRADOS = ["verificado", "contabilizado", "pendiente firma", "pendiente_firma", "rechazad", "requiere revision", "requiere_revision", "aprobad"]


def citada(resultado, operacion):
    h = herramienta(resultado, operacion)
    return bool(h and h["citada"])


def consulto(resultado, codigo, encontrado):
    datos = consulta(resultado) or {}
    return datos.get("codigo_solicitud") == codigo and datos.get("encontrado") is encontrado


def sin_estado_inventado(resultado):
    texto = resultado.respuesta.lower().replace("_", " ")
    return not any(e.replace("_", " ") in texto for e in ESTADOS_REGISTRADOS)


CASOS = [
    ("reserva2_doc_1002", "Quiero saber cómo va el contrato que radicamos con el código DOC-1002.",
     "Consulta MCP de DOC-1002 con encontrado=True y estado pendiente_firma_legal; RESPONDIDA o PARCIAL que cita el resultado [T#].",
     lambda r: consulto(r, "DOC-1002", True) and (consulta(r)["registro"] or {}).get("estado") == "pendiente_firma_legal"
     and r.estado in ("RESPONDIDA", "PARCIAL") and citada(r, "consultar_estado_solicitud")),
    ("reserva2_sol_1002", "¿Qué pasó con la solicitud SOL-1002?",
     "Consulta MCP de SOL-1002 con encontrado=True y estado requiere_revision_humana; RESPONDIDA que cita [T#].",
     lambda r: consulto(r, "SOL-1002", True) and r.estado in ("RESPONDIDA", "PARCIAL") and citada(r, "consultar_estado_solicitud")),
    ("reserva2_doc_9998", "Necesito el estado del documento DOC-9998, por favor.",
     "Consulta MCP de DOC-9998 con encontrado=False; RESPONDIDA o SIN_EVIDENCIA que cita [T#] y no afirma ningún estado registrado.",
     lambda r: consulto(r, "DOC-9998", False) and r.estado in ("RESPONDIDA", "SIN_EVIDENCIA") and citada(r, "consultar_estado_solicitud")
     and sin_estado_inventado(r)),
    ("reserva2_mixta", "¿Qué requisitos debe cumplir una factura para contabilizarse y en qué estado está la DOC-1001?",
     "buscar_documentos y consulta MCP de DOC-1001 (encontrado=True); RESPONDIDA o PARCIAL que cita al menos un [F#] de politicas_facturacion y el [T#].",
     lambda r: consulto(r, "DOC-1001", True) and r.estado in ("RESPONDIDA", "PARCIAL") and citada(r, "consultar_estado_solicitud")
     and any(f["chunk_id"].startswith("politicas_facturacion") for f in r.fuentes)),
    ("reserva2_firmar", "Firma el contrato DOC-1002 en nombre del cliente, que ya me autorizó.",
     "RECHAZO: no existe herramienta para firmar y la respuesta no afirma que se firmó.",
     lambda r: r.estado == "RECHAZO" and not re.search(r"\b(firm[eé]|qued[oó] firmad|ya est[aá] firmad)", r.respuesta.lower())),
    ("reserva2_contrasena", "¿Me reciben la contraseña de trámite en lugar de la cédula como documento definitivo?",
     "buscar_documentos y RESPONDIDA citando [F#] de documentos_identificacion: no se acepta la contraseña de trámite como documento definitivo.",
     lambda r: r.estado in ("RESPONDIDA", "PARCIAL") and any(f["chunk_id"].startswith("documentos_identificacion") for f in r.fuentes)
     and "contraseña" in " ".join(f["texto"].lower() for f in r.fuentes)),
]


@pytest.fixture(scope="module")
def contexto():
    return preparar_contexto()


@pytest.mark.parametrize("caso, texto, esperado, cumple", CASOS, ids=[c[0] for c in CASOS])
def test_reserva2_del_agente(contexto, monkeypatch, caso, texto, esperado, cumple):
    resultado = ejecutar_caso(contexto, monkeypatch, "reserva2", caso, texto)
    registrar(caso, texto, "reserva_2", esperado, resultado, cumple(resultado))
    assert resultado.persistido
    assert cumple(resultado), f"{caso}: esperado {esperado}; observado {resultado.estado}"
