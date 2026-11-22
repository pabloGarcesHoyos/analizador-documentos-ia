import asyncio
import json
import os
import time
from pathlib import Path

import pytest
from dotenv import dotenv_values

import sistema as si

CARPETA_APP = Path(__file__).resolve().parents[1]
PRESUPUESTO_CASO = 4500


def herramienta(resultado, operacion):
    return next((h for h in resultado.herramientas if h["operacion"] == operacion), None)


def clasificacion(resultado):
    h = herramienta(resultado, "clasificar_documento")
    return h["resultado"]["decision"] if h else None


def consulta(resultado):
    h = herramienta(resultado, "consultar_estado_solicitud")
    return h["resultado"] if h else None


def preparar_contexto():
    entorno = {}
    for nombre in (".env", ".env.pruebas"):
        ruta = CARPETA_APP / nombre
        if not ruta.exists():
            pytest.skip(f"Falta app/{nombre}")
        entorno.update({k: v for k, v in dotenv_values(ruta).items() if v})
    if not entorno.get("GROQ_API_KEY"):
        pytest.skip("Falta GROQ_API_KEY en app/.env")
    configuracion = si.ConfiguracionSistema.desde_entorno(entorno)
    from supabase import ClientOptions, create_client
    cliente = create_client(configuracion.supabase.url, configuracion.supabase.clave_publicable,
                            options=ClientOptions(persist_session=False, auto_refresh_token=False))
    sesion = cliente.auth.sign_in_with_password({"email": entorno["PRUEBA_A_EMAIL"], "password": entorno["PRUEBA_A_PASSWORD"]})
    return si.Sistema(configuracion), sesion.session.access_token


def ejecutar_caso(contexto, monkeypatch, prefijo, caso, texto, fallo=False):
    sistema, token = contexto
    time.sleep(sistema.cupo.segundos_para(PRESUPUESTO_CASO))
    if fallo:
        while sistema.cupo.usados() > 0:
            time.sleep(1)
        monkeypatch.setenv("MCP_FALLO_FORZADO", "1")
    conversacion = sistema.almacen.crear_conversacion(token, f"{prefijo}-{caso}")
    return asyncio.run(sistema.atender(texto, conversacion["id"], token))


def registrar(caso, texto, esperado, criterio, resultado, cumple):
    if not os.environ.get("REGRESION_SALIDA"):
        return
    traza = resultado.traza
    registro = {"caso": caso, "entrada": texto, "esperado_corte1": esperado, "criterio": criterio,
                "estado_final": resultado.estado, "cumple": bool(cumple), "persistido": resultado.persistido,
                "respuesta": resultado.respuesta, "limitacion": resultado.limitacion, "detalle_error": resultado.detalle_error,
                "flujo": traza.get("flujo"), "ruta": traza.get("ruta"), "codigos": traza.get("codigos"), "origen_codigos": traza.get("origen_codigos"),
                "decision_enrutador": traza.get("decision_enrutador"), "operaciones": traza.get("operaciones"), "llamadas_modelo": traza.get("llamadas_modelo"),
                "reintento_redaccion": traza.get("reintento_redaccion"), "eventos": traza.get("eventos"), "error_tecnico": traza.get("error_tecnico"),
                "salidas_rechazadas": traza.get("salidas_rechazadas"), "prompt_rag": traza.get("prompt_rag"),
                "frases_generadas": traza.get("frases_generadas"), "error_proveedor": traza.get("error_proveedor"),
                "herramientas": [{"etiqueta": h["etiqueta"], "operacion": h["operacion"], "argumentos": h["argumentos"], "citada": h["citada"],
                                  "decision": h["resultado"].get("decision"), "encontrado": h["resultado"].get("encontrado"),
                                  "estado": (h["resultado"].get("registro") or {}).get("estado"), "fuente": h["resultado"].get("fuente")}
                                 for h in resultado.herramientas],
                "fuentes": [f["chunk_id"] for f in resultado.fuentes], "duracion_ms": traza.get("duracion_ms"),
                "tokens": traza.get("tokens"), "llamadas": traza.get("llamadas")}
    carpeta = Path(os.environ["REGRESION_SALIDA"])
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{caso}.json").write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
