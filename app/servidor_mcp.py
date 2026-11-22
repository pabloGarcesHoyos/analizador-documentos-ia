import os
from typing import Annotated

from mcp.server import MCPServer
from pydantic import BaseModel, Field

PATRON_CODIGO = r"^(?:DOC|SOL)-[0-9]{4}$"

REGISTROS = {
    "DOC": {
        "fuente": "registro_sistema_documental_v1",
        "origen": "corte 2, registro documental ficticio de la herramienta del corte 1",
        "datos": {
            "DOC-1001": {"tipo": "factura", "estado": "verificado_y_contabilizado", "emisor": "TechCorp S.A.",
                         "monto": "$1,500.00 USD", "fecha_proceso": "2026-08-12"},
            "DOC-1002": {"tipo": "contrato", "estado": "pendiente_firma_legal", "partes": "Servicios Prof. / Cliente",
                         "fecha_proceso": "2026-09-01"},
            "DOC-1003": {"tipo": "identificacion", "estado": "rechazado_imagen_borrosa", "titular": "Titular ficticio 03",
                         "fecha_proceso": "2026-09-05"},
        },
    },
    "SOL": {
        "fuente": "sistema_seguimiento_expedientes",
        "origen": "clase 11, solicitudes ficticias del servidor MCP de seguimiento",
        "datos": {
            "SOL-1001": {"categoria": "contratacion", "estado": "pendiente_firma",
                         "detalle": "Contrato legal generado pendiente de validación de cédula."},
            "SOL-1002": {"categoria": "contratacion", "estado": "requiere_revision_humana",
                         "detalle": "Intento de modificación de cláusulas fuera del procedimiento."},
        },
    },
}

mcp = MCPServer("Seguimiento de documentos y solicitudes")


class ResultadoEstado(BaseModel):
    codigo_solicitud: str
    encontrado: bool
    registro: dict[str, str] | None
    fuente: str
    origen: str


@mcp.tool()
def consultar_estado_solicitud(
    codigo_solicitud: Annotated[str, Field(pattern=PATRON_CODIGO, description="Código DOC-XXXX o SOL-XXXX escrito por el usuario.")],
) -> ResultadoEstado:
    """Consulta el estado registrado de un documento (DOC-XXXX) o de una solicitud (SOL-XXXX). Solo lectura: no registra, aprueba, firma, modifica ni elimina."""
    if os.environ.get("MCP_FALLO_FORZADO") == "1":
        raise RuntimeError("Fallo controlado del registro de seguimiento.")
    registro = REGISTROS[codigo_solicitud[:3]]
    datos = registro["datos"].get(codigo_solicitud)
    return ResultadoEstado(codigo_solicitud=codigo_solicitud, encontrado=datos is not None,
                           registro=dict(datos) if datos else None, fuente=registro["fuente"], origen=registro["origen"])


if __name__ == "__main__":
    mcp.run(transport="stdio")
