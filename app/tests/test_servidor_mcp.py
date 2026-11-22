import asyncio
import os
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters, stdio_client

SERVIDOR = Path(__file__).resolve().parents[1] / "servidor_mcp.py"


def parametros(fallo=False):
    entorno = {"PYTHONIOENCODING": "utf-8", "PATH": os.environ.get("PATH", "")}
    if fallo:
        entorno["MCP_FALLO_FORZADO"] = "1"
    return StdioServerParameters(command=sys.executable, args=[str(SERVIDOR)], env=entorno)


async def _con_cliente(accion, fallo=False):
    async with Client(stdio_client(parametros(fallo)), read_timeout_seconds=30) as cliente:
        return await accion(cliente)


def ejecutar(accion, fallo=False):
    return asyncio.run(_con_cliente(accion, fallo))


def llamar(codigo, fallo=False):
    return ejecutar(lambda c: c.call_tool("consultar_estado_solicitud", {"codigo_solicitud": codigo}), fallo)


def test_publica_una_sola_herramienta_con_el_patron_del_codigo():
    listado = ejecutar(lambda c: c.list_tools())
    assert [h.name for h in listado.tools] == ["consultar_estado_solicitud"]
    herramienta = listado.tools[0]
    propiedad = herramienta.input_schema["properties"]["codigo_solicitud"]
    assert propiedad["pattern"] == "^(?:DOC|SOL)-[0-9]{4}$"
    assert herramienta.input_schema["required"] == ["codigo_solicitud"]
    assert "Solo lectura" in herramienta.description


@pytest.mark.parametrize("codigo, estado, fuente", [
    ("DOC-1001", "verificado_y_contabilizado", "registro_sistema_documental_v1"),
    ("DOC-1002", "pendiente_firma_legal", "registro_sistema_documental_v1"),
    ("DOC-1003", "rechazado_imagen_borrosa", "registro_sistema_documental_v1"),
    ("SOL-1001", "pendiente_firma", "sistema_seguimiento_expedientes"),
    ("SOL-1002", "requiere_revision_humana", "sistema_seguimiento_expedientes"),
])
def test_registro_y_fuente_de_cada_codigo(codigo, estado, fuente):
    resultado = llamar(codigo)
    assert not resultado.is_error
    datos = resultado.structured_content
    assert datos["codigo_solicitud"] == codigo and datos["encontrado"] is True
    assert datos["registro"]["estado"] == estado and datos["fuente"] == fuente


def test_registro_del_corte2_sin_cambios():
    datos = llamar("DOC-1001").structured_content
    assert datos["registro"] == {"tipo": "factura", "estado": "verificado_y_contabilizado", "emisor": "TechCorp S.A.",
                                 "monto": "$1,500.00 USD", "fecha_proceso": "2026-08-12"}
    assert datos["origen"].startswith("corte 2")


def test_codigo_valido_inexistente():
    datos = llamar("DOC-9999").structured_content
    assert datos["encontrado"] is False and datos["registro"] is None and datos["fuente"] == "registro_sistema_documental_v1"


@pytest.mark.parametrize("codigo", ["1001", "doc-1001", "DOC-10011", "FAC-1001", "DOC-1001; DROP"])
def test_codigo_con_formato_invalido_es_rechazado(codigo):
    assert llamar(codigo).is_error


def test_argumentos_extra_o_faltantes_son_rechazados():
    assert ejecutar(lambda c: c.call_tool("consultar_estado_solicitud", {})).is_error


def test_fallo_controlado_se_informa_como_error():
    assert llamar("DOC-1001", fallo=True).is_error
