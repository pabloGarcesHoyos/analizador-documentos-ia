from pathlib import Path

import yaml

import app as ap
import sistema as si

RAIZ = Path(__file__).resolve().parents[2]
SECRETOS = {"SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "GROQ_API_KEY", "CORPUS_ID", "CORPUS_PROPIETARIO_ID"}


def servicio() -> dict:
    return yaml.safe_load((RAIZ / "render.yaml").read_text(encoding="utf-8"))["services"][0]


def test_servicio_web_con_root_directory_app():
    datos = servicio()
    assert (datos["type"], datos["runtime"], datos["rootDir"], datos["startCommand"]) == ("web", "python", "app", "python app.py")
    pasos = datos["buildCommand"].split(" && ")
    assert pasos == ["pip install -r requirements.txt", "python descargar_modelos.py", "npm ci --prefix mcp_archivos --omit=dev"]
    assert (RAIZ / "app/requirements.txt").exists() and (RAIZ / "app/mcp_archivos/package-lock.json").exists()


def test_variables_sin_valores_secretos_y_completas():
    variables = {v["key"]: v for v in servicio()["envVars"]}
    assert all(variables[n].get("sync") is False and "value" not in variables[n] for n in SECRETOS)
    assert variables["PYTHON_VERSION"]["value"].startswith("3.13.") and variables["GRADIO_SERVER_NAME"]["value"] == "0.0.0.0"
    assert "PORT" not in variables
    entorno = {n: v.get("value", "valor") for n, v in variables.items()}
    entorno.update(SUPABASE_URL="https://p.supabase.co", SUPABASE_PUBLISHABLE_KEY="sb_publishable_x", CORPUS_PROPIETARIO_ID="11111111-2222-3333-4444-555555555555")
    configuracion, servidor, puerto = ap.cargar_configuracion({**entorno, "PORT": "10000"})
    assert (servidor, puerto) == ("0.0.0.0", 10000) and configuracion.recuperacion in ("C_DEMANDA", "B")
    assert isinstance(si.ConfiguracionSistema.desde_entorno(entorno), si.ConfiguracionSistema)
