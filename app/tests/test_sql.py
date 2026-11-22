import re
from pathlib import Path

import pytest

CARPETA = Path(__file__).resolve().parents[1] / "sql"
ARCHIVOS = sorted(CARPETA.glob("*.sql"))
ESQUEMA = "\n".join(a.read_text(encoding="utf-8") for a in ARCHIVOS if not a.name.startswith("04_"))
TABLAS = sorted(set(re.findall(r"create table if not exists public\.(\w+)", ESQUEMA)))


def sin_literales(texto):
    return re.sub(r"\$\$.*?\$\$", "", re.sub(r"'[^']*'", "''", texto), flags=re.S)


def test_scripts_numerados_en_orden():
    assert [a.name for a in ARCHIVOS] == ["01_corpus.sql", "02_historial.sql", "03_informes.sql", "04_comprobaciones.sql", "05_presentacion.sql", "06_propuesta_informe.sql"]


@pytest.mark.parametrize("archivo", ARCHIVOS, ids=lambda a: a.name)
def test_sin_comentarios(archivo):
    texto = sin_literales(archivo.read_text(encoding="utf-8"))
    assert "--" not in texto and "/*" not in texto


@pytest.mark.parametrize("archivo", [a for a in ARCHIVOS if not a.name.startswith("04_")], ids=lambda a: a.name)
def test_transaccion_e_idempotencia(archivo):
    texto = archivo.read_text(encoding="utf-8")
    assert texto.strip().startswith("begin;") and texto.strip().endswith("commit;")
    for politica in re.findall(r"create policy (\w+)", texto):
        assert f"drop policy if exists {politica} " in texto
    assert not re.search(r"create table (?!if not exists)", texto)
    assert not re.search(r"create index (?!if not exists)", texto)


def test_tablas_esperadas():
    assert TABLAS == ["acciones_informe", "analizador_fragmentos", "conversaciones", "lectores_corpus", "mensajes"]


@pytest.mark.parametrize("tabla", TABLAS)
def test_cada_tabla_con_rls_y_sin_acceso_anonimo(tabla):
    assert f"alter table public.{tabla} enable row level security;" in ESQUEMA
    assert f"revoke all on public.{tabla} from public, anon, authenticated;" in ESQUEMA
    for permiso in re.findall(rf"grant ([^;]+) on public\.{tabla} to (\w+);", ESQUEMA):
        assert permiso[1] == "authenticated"


def test_nada_desactiva_controles_ni_usa_claves_administrativas():
    texto = ESQUEMA.lower()
    for prohibido in ("disable row level security", "no force row level security", "service_role", "security definer", "to anon", "to public"):
        assert prohibido not in texto


def test_politicas_solo_para_usuarios_autenticados():
    politicas = re.findall(r"create policy \w+ on public\.\w+\s+for (\w+) to (\w+)", ESQUEMA)
    assert politicas and all(rol == "authenticated" for _, rol in politicas)


def test_historial_solo_select_e_insert_propios():
    historial = (CARPETA / "02_historial.sql").read_text(encoding="utf-8")
    assert sorted(re.findall(r"for (\w+) to authenticated", historial)) == ["insert", "insert", "select", "select"]
    assert "grant select, insert on public.conversaciones to authenticated;" in historial
    assert "grant select, insert on public.mensajes to authenticated;" in historial
    assert "foreign key (conversacion_id, usuario_id)\n    references public.conversaciones (id, usuario_id)" in historial
    assert historial.count("c.usuario_id = (select auth.uid())") == 2


def test_funcion_de_busqueda_invoker_sin_filtrar_por_auth_uid():
    corpus = (CARPETA / "01_corpus.sql").read_text(encoding="utf-8")
    funcion = re.search(r"create or replace function public\.analizador_buscar_fragmentos_autorizado.*?\$\$(.*?)\$\$;", corpus, re.S)
    assert funcion
    cabecera = funcion.group(0).split("$$")[0]
    assert "security invoker" in cabecera and "set search_path = ''" in cabecera
    assert "auth.uid()" not in funcion.group(1)
    assert "d.owner_id = p_propietario_id" in funcion.group(1)
    assert "limit least(greatest(coalesce(match_count, 10), 1), 10)" in funcion.group(1)


def test_lectores_no_pueden_autorizarse_a_si_mismos():
    corpus = (CARPETA / "01_corpus.sql").read_text(encoding="utf-8")
    assert "grant select on public.lectores_corpus to authenticated;" in corpus
    assert not re.search(r"grant [^;]*(insert|update|delete)[^;]* on public\.lectores_corpus", corpus)


def test_informes_unicos_y_resultado_una_sola_vez():
    informes = (CARPETA / "03_informes.sql").read_text(encoding="utf-8")
    assert "unique (usuario_id, mensaje_id)" in informes
    assert "grant update (resultado) on public.acciones_informe to authenticated;" in informes
    assert "using (usuario_id = (select auth.uid()) and decision = 'aprobada' and resultado is null)" in informes


def test_presentacion_agrega_columnas_sin_tocar_permisos_ni_politicas():
    texto = (CARPETA / "05_presentacion.sql").read_text(encoding="utf-8")
    assert "add column if not exists limitacion text not null default ''" in texto
    assert "add column if not exists detalle_error text not null default ''" in texto
    assert texto.count("if not exists (select 1 from pg_constraint") == 3
    assert "grant" not in texto and "policy" not in texto and "drop" not in texto


def test_propuesta_de_informe_con_columna_validada_sin_tocar_permisos():
    texto = (CARPETA / "06_propuesta_informe.sql").read_text(encoding="utf-8")
    assert "add column if not exists propuesta_informe jsonb" in texto and "rol = 'asistente'" in texto
    assert "^[0-9a-f]{64}$" in texto and "^informe_[0-9a-f]{12}[.]md$" in texto
    assert "grant" not in texto and "policy" not in texto and "drop" not in texto
