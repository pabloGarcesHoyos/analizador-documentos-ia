import re

import pytest

from casos_agente import clasificacion, consulta, ejecutar_caso, herramienta, preparar_contexto, registrar

pytestmark = [pytest.mark.integracion, pytest.mark.groq, pytest.mark.reserva3]


def consultas(resultado):
    return {h["resultado"]["codigo_solicitud"]: h for h in resultado.herramientas if h["operacion"] == "consultar_estado_solicitud"}


def sin_etiquetas(resultado):
    return not re.search(r"\[[FT]\d", resultado.respuesta)


CASOS = [
    ("reserva3_doc_1001_informal", "oye, la factura DOC-1001 ya pasó?",
     "Ruta de estado: consulta MCP de DOC-1001 (encontrado=True) y RESPONDIDA con la frase del programa citando [T1]; sin llamadas al modelo.",
     lambda r: r.traza.get("ruta") == "estado" and consulta(r) and consulta(r)["encontrado"] is True and herramienta(r, "consultar_estado_solicitud")["citada"]
     and r.estado == "RESPONDIDA" and "verificado_y_contabilizado [T1]" in r.respuesta and not r.traza.get("llamadas")),
    ("reserva3_dos_codigos", "¿Cómo van DOC-1003 y SOL-1002?",
     "Ruta de estado con dos consultas MCP (DOC-1003 y SOL-1002, ambas encontradas), cada frase con su [T#] y RESPONDIDA.",
     lambda r: r.traza.get("ruta") == "estado" and set(consultas(r)) == {"DOC-1003", "SOL-1002"}
     and all(h["citada"] for h in consultas(r).values()) and r.estado == "RESPONDIDA"),
    ("reserva3_sol_0042", "Estado de SOL-0042",
     "Ruta de estado: consulta MCP de SOL-0042 con encontrado=False; la respuesta dice que no existe en el registro, cita [T1] y no inventa un estado.",
     lambda r: r.traza.get("ruta") == "estado" and consulta(r) and consulta(r)["encontrado"] is False and "no existe en el registro" in r.respuesta
     and herramienta(r, "consultar_estado_solicitud")["citada"]),
    ("reserva3_contrato_arriendo", "Contrato de arrendamiento entre Inmobiliaria Ejemplo S.A.S. y Cliente Ficticio. Objeto: arriendo de oficina. Valor mensual: $2.000.000. Vigencia: 12 meses. Firmado por ambas partes.",
     "Ruta de documento: clasificador del corte 1; si decide OK_VALIDADO, RESPONDIDA con la clasificación citando [T1]; si decide OK_PIDE_ACLARACION, ACLARACION; si OK_REQUIERE_HUMANO, RECHAZO.",
     lambda r: r.traza.get("ruta") == "documento" and clasificacion(r) in ("OK_VALIDADO", "OK_PIDE_ACLARACION", "OK_REQUIERE_HUMANO")
     and r.estado == {"OK_VALIDADO": "RESPONDIDA", "OK_PIDE_ACLARACION": "ACLARACION", "OK_REQUIERE_HUMANO": "RECHAZO"}[clasificacion(r)]),
    ("reserva3_registrar_factura", "¿Puedo pedirle al analizador que registre una factura por mí?",
     "Ruta RAG: busca en las políticas y responde (RESPONDIDA o PARCIAL) que el analizador solo consulta y no registra, citando [F#] de seguimiento_y_seguridad.",
     lambda r: r.traza.get("ruta") == "rag" and r.estado in ("RESPONDIDA", "PARCIAL")
     and any(f["chunk_id"].startswith("seguimiento_y_seguridad") for f in r.fuentes)),
    ("reserva3_saludo", "Hola, buenos días, ¿en qué me puedes ayudar?",
     "Ruta libre: una sola llamada al modelo que elige aclarar el alcance; ACLARACION sin herramientas ni etiquetas.",
     lambda r: r.traza.get("ruta") == "libre" and r.estado == "ACLARACION" and not r.herramientas and sin_etiquetas(r)),
]


@pytest.fixture(scope="module")
def contexto():
    return preparar_contexto()


@pytest.mark.parametrize("caso, texto, esperado, cumple", CASOS, ids=[c[0] for c in CASOS])
def test_reserva3_del_flujo(contexto, monkeypatch, caso, texto, esperado, cumple):
    resultado = ejecutar_caso(contexto, monkeypatch, "reserva3", caso, texto)
    registrar(caso, texto, "reserva_3", esperado, resultado, bool(cumple(resultado)))
    assert resultado.persistido
    assert cumple(resultado), f"{caso}: esperado {esperado}; observado {resultado.estado}"
