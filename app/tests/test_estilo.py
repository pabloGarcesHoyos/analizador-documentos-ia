import ast
import io
import re
import subprocess
import tokenize
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
ARCHIVOS = [RAIZ / r for r in subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                                             cwd=RAIZ, capture_output=True, text=True, check=True).stdout.splitlines()]
TEXTOS = [a for a in ARCHIVOS if a.suffix in {".py", ".sql", ".md", ".txt", ".ini", ".ejemplo", ".toml", ".json", ".yaml", ".yml"} or a.name.startswith(".")]
PYTHON = [a for a in ARCHIVOS if a.suffix == ".py"]
CONFIGURACION = [a for a in ARCHIVOS if a.suffix in {".ini", ".txt", ".ejemplo", ".toml"} or a.name == ".gitignore"]
PROHIBIDAS = ["cla" + "ude", "anthro" + "pic", "co-authored" + "-by", "generated" + " with", "chat" + "gpt", "open" + "ai/gpt-4"]
DECORATIVOS = re.compile("[" + "".join(map(chr, (0x00B7, 0x2192, 0x2190, 0x2248, 0x2705, 0x2714, 0x2728, 0x274C))) + chr(0x1F300) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF) + "]")


def relativo(ruta):
    return str(ruta.relative_to(RAIZ))


@pytest.mark.parametrize("archivo", PYTHON, ids=relativo)
def test_python_sin_comentarios(archivo):
    comentarios = [t for t in tokenize.generate_tokens(io.StringIO(archivo.read_text(encoding="utf-8")).readline) if t.type == tokenize.COMMENT]
    assert comentarios == []


@pytest.mark.parametrize("archivo", PYTHON, ids=relativo)
def test_python_sin_docstrings_salvo_herramientas_mcp(archivo):
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    for nodo in [arbol, *ast.walk(arbol)]:
        if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(nodo) is not None:
            es_herramienta = archivo.name == "servidor_mcp.py" and isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                "tool" in ast.unparse(d) for d in nodo.decorator_list)
            assert es_herramienta, f"docstring en {getattr(nodo, 'name', 'modulo')}"


@pytest.mark.parametrize("archivo", CONFIGURACION, ids=relativo)
def test_configuracion_sin_comentarios(archivo):
    assert not [linea for linea in archivo.read_text(encoding="utf-8").splitlines() if linea.lstrip().startswith(("#", ";"))]


@pytest.mark.parametrize("archivo", TEXTOS, ids=relativo)
def test_sin_rastros_ni_decorativos(archivo):
    texto = archivo.read_text(encoding="utf-8")
    minusculas = texto.lower()
    assert [p for p in PROHIBIDAS if p in minusculas] == []
    assert DECORATIVOS.findall(texto) == []
