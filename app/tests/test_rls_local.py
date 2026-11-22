import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.sql_local

URL = os.environ.get("PRUEBAS_PG_URL", "")
CARPETA_SQL = Path(__file__).resolve().parents[1] / "sql"
MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
HUELLA = hashlib.sha256(b"contenido").hexdigest()


def vector(semilla):
    valores = [((semilla * 31 + i * 7) % 97) / 97 for i in range(384)]
    return "[" + ",".join(f"{v:.5f}" for v in valores) + "]"


@pytest.fixture(scope="module")
def conexion():
    if not URL:
        pytest.skip("PRUEBAS_PG_URL no está definida")
    with psycopg.connect(URL, autocommit=True) as conexion:
        for nombre in ("01_corpus.sql", "02_historial.sql", "03_informes.sql", "05_presentacion.sql", "05_presentacion.sql"):
            conexion.execute((CARPETA_SQL / nombre).read_text(encoding="utf-8"))
        yield conexion


@pytest.fixture(scope="module")
def usuarios(conexion):
    ids = {nombre: str(uuid.uuid4()) for nombre in ("propietario", "lector", "ajeno")}
    for nombre, identificador in ids.items():
        conexion.execute("insert into auth.users (id, email) values (%s, %s)", (identificador, f"{nombre}-{identificador[:8]}@prueba.local"))
    yield ids
    conexion.execute("delete from public.analizador_fragmentos where owner_id = any(%s::uuid[])", (list(ids.values()),))
    conexion.execute("delete from auth.users where id = any(%s::uuid[])", (list(ids.values()),))


@contextmanager
def como(conexion, usuario_id=None, rol="authenticated"):
    with conexion.transaction():
        conexion.execute(f"set local role {rol}")
        if usuario_id:
            conexion.execute("select set_config('request.jwt.claims', %s, true), set_config('request.jwt.claim.sub', %s, true)",
                             (json.dumps({"sub": usuario_id, "role": rol}), usuario_id))
        yield conexion


def falla(conexion, usuario_id, sql, parametros=(), rol="authenticated"):
    with pytest.raises(psycopg.Error) as error:
        with como(conexion, usuario_id, rol) as c:
            c.execute(sql, parametros)
    return error.value.sqlstate


def nueva_conversacion(conexion, usuario_id, titulo="Prueba"):
    with como(conexion, usuario_id) as c:
        return str(c.execute("insert into public.conversaciones (titulo) values (%s) returning id", (titulo,)).fetchone()[0])


def nuevo_mensaje(conexion, usuario_id, conversacion_id, rol="asistente"):
    with como(conexion, usuario_id) as c:
        return c.execute("insert into public.mensajes (conversacion_id, rol, contenido) values (%s, %s, 'texto') returning id",
                         (conversacion_id, rol)).fetchone()[0]


def test_otro_usuario_no_ve_la_conversacion_ni_sus_mensajes(conexion, usuarios):
    propia = nueva_conversacion(conexion, usuarios["lector"])
    nuevo_mensaje(conexion, usuarios["lector"], propia, rol="usuario")
    with como(conexion, usuarios["ajeno"]) as c:
        assert c.execute("select count(*) from public.conversaciones where id = %s", (propia,)).fetchone()[0] == 0
        assert c.execute("select count(*) from public.mensajes where conversacion_id = %s", (propia,)).fetchone()[0] == 0
    with como(conexion, usuarios["lector"]) as c:
        assert c.execute("select count(*) from public.mensajes where conversacion_id = %s", (propia,)).fetchone()[0] == 1


def test_otro_usuario_no_inserta_en_conversacion_ajena(conexion, usuarios):
    propia = nueva_conversacion(conexion, usuarios["lector"])
    assert falla(conexion, usuarios["ajeno"], "insert into public.mensajes (conversacion_id, rol, contenido) values (%s, 'usuario', 'intruso')",
                 (propia,)) in {"23503", "42501"}
    assert falla(conexion, usuarios["ajeno"], "insert into public.mensajes (conversacion_id, usuario_id, rol, contenido) values (%s, %s, 'usuario', 'intruso')",
                 (propia, usuarios["lector"])) == "42501"
    assert falla(conexion, usuarios["ajeno"], "insert into public.conversaciones (usuario_id, titulo) values (%s, 'suplantada')",
                 (usuarios["lector"],)) == "42501"


def test_orden_estable_de_mensajes(conexion, usuarios):
    propia = nueva_conversacion(conexion, usuarios["lector"])
    ids = [nuevo_mensaje(conexion, usuarios["lector"], propia, rol=r) for r in ("usuario", "asistente", "usuario", "asistente")]
    assert ids == sorted(ids)


def test_sin_borrado_ni_edicion_del_historial(conexion, usuarios):
    propia = nueva_conversacion(conexion, usuarios["lector"])
    assert falla(conexion, usuarios["lector"], "delete from public.conversaciones where id = %s", (propia,)) == "42501"
    assert falla(conexion, usuarios["lector"], "update public.conversaciones set titulo = 'otro' where id = %s", (propia,)) == "42501"


def test_anonimo_sin_acceso(conexion):
    for tabla in ("conversaciones", "mensajes", "acciones_informe", "analizador_fragmentos", "lectores_corpus"):
        assert falla(conexion, None, f"select count(*) from public.{tabla}", rol="anon") == "42501"


def test_lector_autorizado_busca_en_el_corpus_y_el_ajeno_no(conexion, usuarios):
    corpus = f"corpus_prueba_{uuid.uuid4().hex[:8]}"
    configuracion = json.dumps({"modelo": MODELO, "revision": REVISION})
    with como(conexion, usuarios["propietario"]) as c:
        for numero in range(3):
            c.execute("insert into public.analizador_fragmentos (corpus_id, chunk_id, content, metadata, configuracion, embedding) "
                      "values (%s, %s, %s, '{}'::jsonb, %s::jsonb, %s::extensions.vector)",
                      (corpus, f"frag:{numero}", f"texto {numero}", configuracion, vector(numero)))
    conexion.execute("insert into public.lectores_corpus (propietario_id, corpus_id, lector_id) values (%s, %s, %s)",
                     (usuarios["propietario"], corpus, usuarios["lector"]))
    consulta = "select chunk_id from public.analizador_buscar_fragmentos_autorizado(%s::extensions.vector, %s, %s, %s, %s, 10)"
    parametros = (vector(1), usuarios["propietario"], corpus, MODELO, REVISION)
    with como(conexion, usuarios["lector"]) as c:
        resultado = [f[0] for f in c.execute(consulta, parametros).fetchall()]
        assert resultado[0] == "frag:1" and len(resultado) == 3
        assert c.execute("select count(*) from public.analizador_fragmentos where corpus_id = %s", (corpus,)).fetchone()[0] == 3
    with como(conexion, usuarios["ajeno"]) as c:
        assert c.execute(consulta, parametros).fetchall() == []
        assert c.execute("select count(*) from public.analizador_fragmentos where corpus_id = %s", (corpus,)).fetchone()[0] == 0
    with como(conexion, usuarios["propietario"]) as c:
        assert len(c.execute(consulta, parametros).fetchall()) == 3
    with como(conexion, usuarios["lector"]) as c:
        assert c.execute("update public.analizador_fragmentos set content = 'alterado' where corpus_id = %s returning 1", (corpus,)).fetchall() == []
    assert falla(conexion, usuarios["ajeno"], "insert into public.lectores_corpus (propietario_id, corpus_id, lector_id) values (%s, %s, %s)",
                 (usuarios["propietario"], corpus, usuarios["ajeno"])) == "42501"
    assert falla(conexion, usuarios["lector"], "insert into public.analizador_fragmentos (owner_id, corpus_id, chunk_id, content, metadata, configuracion, embedding) "
                 "values (%s, %s, 'frag:9', 'x', '{}'::jsonb, '{}'::jsonb, %s::extensions.vector)",
                 (usuarios["propietario"], corpus, vector(9))) == "42501"


def test_acciones_de_informe_unicas_y_resultado_una_vez(conexion, usuarios):
    propia = nueva_conversacion(conexion, usuarios["lector"])
    mensaje = nuevo_mensaje(conexion, usuarios["lector"], propia)
    insertar = ("insert into public.acciones_informe (conversacion_id, mensaje_id, decision, destino, huella_contenido) "
                "values (%s, %s, 'aprobada', 'informe.md', %s) returning id")
    with como(conexion, usuarios["lector"]) as c:
        accion = c.execute(insertar, (propia, mensaje, HUELLA)).fetchone()[0]
    assert falla(conexion, usuarios["lector"], insertar, (propia, mensaje, HUELLA)) == "23505"
    assert falla(conexion, usuarios["ajeno"], insertar, (propia, mensaje, HUELLA)) in {"23503", "42501"}
    assert falla(conexion, usuarios["lector"], "update public.acciones_informe set decision = 'rechazada' where id = %s", (accion,)) == "42501"
    with como(conexion, usuarios["ajeno"]) as c:
        assert c.execute("update public.acciones_informe set resultado = 'ejecutada' where id = %s returning id", (accion,)).fetchall() == []
    with como(conexion, usuarios["lector"]) as c:
        assert len(c.execute("update public.acciones_informe set resultado = 'ejecutada' where id = %s returning id", (accion,)).fetchall()) == 1
        assert c.execute("update public.acciones_informe set resultado = 'fallida' where id = %s returning id", (accion,)).fetchall() == []
    otra = nueva_conversacion(conexion, usuarios["lector"])
    sin_accion = nuevo_mensaje(conexion, usuarios["lector"], propia)
    assert falla(conexion, usuarios["lector"], insertar, (otra, sin_accion, HUELLA)) == "23503"


def test_presentacion_del_mensaje_se_guarda_y_sigue_siendo_privada(conexion, usuarios):
    propia = nueva_conversacion(conexion, usuarios["lector"])
    with como(conexion, usuarios["lector"]) as c:
        c.execute("insert into public.mensajes (conversacion_id, rol, contenido, estado, limitacion, detalle_error) "
                  "values (%s, 'asistente', 'texto', 'PARCIAL', 'Falta una parte.', '')", (propia,))
        assert c.execute("select limitacion, detalle_error from public.mensajes where conversacion_id = %s", (propia,)).fetchone() == ("Falta una parte.", "")
    with como(conexion, usuarios["ajeno"]) as c:
        assert c.execute("select count(*) from public.mensajes where conversacion_id = %s", (propia,)).fetchone()[0] == 0
    assert falla(conexion, usuarios["lector"], "insert into public.mensajes (conversacion_id, rol, contenido, limitacion) values (%s, 'usuario', 'texto', 'x')",
                 (propia,)) == "23514"
    assert falla(conexion, usuarios["lector"], "insert into public.mensajes (conversacion_id, rol, contenido, limitacion) values (%s, 'asistente', 'texto', %s)",
                 (propia, "x" * 2001)) == "23514"
