import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import almacenamiento as al
import cargar_corpus as cc
import descargar_modelos
import recuperacion as rc

DATOS = Path(__file__).resolve().parent / "datos"
CORPUS_CORTE2 = "analizador_documental_v2-057b729f44ae"
sin_modelos = pytest.mark.skipif(bool(descargar_modelos.faltantes()), reason="Faltan los modelos: ejecuta python app/descargar_modelos.py")


class Consulta:
    def __init__(self, cliente, tabla):
        self.cliente = cliente
        self.tabla = tabla
        self.filtros = {}
        self.lote = None

    def select(self, columnas, count=None):
        return self

    def eq(self, columna, valor):
        self.filtros[columna] = valor
        return self

    def limit(self, cantidad):
        return self

    def upsert(self, lote, on_conflict):
        self.lote, self.conflicto = lote, on_conflict
        return self

    def execute(self):
        if self.lote is not None:
            self.cliente.lotes.append((len(self.lote), self.conflicto))
            for fila in self.lote:
                self.cliente.filas[(fila["owner_id"], fila["corpus_id"], fila["chunk_id"])] = fila
            return SimpleNamespace(data=self.lote, count=None)
        cantidad = sum(1 for (dueno, corpus, _) in self.cliente.filas if dueno == self.filtros["owner_id"] and corpus == self.filtros["corpus_id"])
        return SimpleNamespace(data=[], count=cantidad - self.cliente.perdidas)


class ClienteFalso:
    def __init__(self, primero=None):
        self.filas = {}
        self.lotes = []
        self.llamadas_rpc = []
        self.primero = primero
        self.perdidas = 0

    def table(self, nombre):
        assert nombre == "analizador_fragmentos"
        return Consulta(self, nombre)

    def rpc(self, nombre, parametros):
        self.llamadas_rpc.append((nombre, parametros))
        propias = [f for f in self.filas.values() if f["owner_id"] == parametros["p_propietario_id"] and f["corpus_id"] == parametros["p_corpus_id"]]
        consulta = np.array(parametros["query_embedding"])
        ordenadas = sorted(propias, key=lambda f: -float(np.array(f["embedding"]) @ consulta))
        datos = [{"chunk_id": self.primero}] if self.primero else [{"chunk_id": f["chunk_id"]} for f in ordenadas[:3]]
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=datos))


def registros_de_prueba(cantidad=60):
    return [{"chunk_id": f"doc:1:parrafos:{i:03d}", "texto": f"texto {i}", "source": "doc.md", "section": "S", "tokens": 5} for i in range(cantidad)]


def codificar_falso(texto):
    semilla = sum(map(ord, texto))
    vector = np.random.default_rng(semilla).normal(size=384).astype(np.float32)
    return vector / np.linalg.norm(vector)


@sin_modelos
def test_reproduce_el_corpus_del_corte2():
    corpus_id, configuracion, registros = cc.preparar()
    referencia = {f["chunk_id"]: f for f in json.loads((DATOS / "fragmentos.json").read_text(encoding="utf-8"))}
    assert corpus_id == CORPUS_CORTE2 and len(registros) == 20 == len(referencia)
    assert {r["chunk_id"]: r["texto"] for r in registros} == {k: v["content"] for k, v in referencia.items()}
    assert configuracion["modelo"] == rc.MODELO_EMBEDDINGS and configuracion["max_seq_length"] == 128 and configuracion["version_corpus"] == "2.0-2026-10"
    assert not any(r["dividido"] for r in registros) and max(r["tokens"] for r in registros) <= 120


@sin_modelos
def test_parrafo_largo_se_divide_en_ventanas_que_caben():
    tokenizador = rc.TokenizadorXLMR(rc.CARPETA_MODELOS / "embeddings/sentencepiece.bpe.model")
    parrafo = " ".join(f"La factura número {i} debe incluir el NIT del emisor y el desglose de impuestos." for i in range(20))
    documento = {"document_id": "largo", "source": "largo.md", "title": "Documento largo", "version": "1", "source_hash": "x",
                 "texto": f"# Documento largo\n\n## Sección\n\n{parrafo}"}
    registros = cc.fragmentar([documento], tokenizador, 120)
    assert len(registros) > 1 and all(r["dividido"] and r["tokens"] <= 120 for r in registros)
    assert all(r["texto"].startswith("Documento largo / Sección\n") for r in registros)
    assert [r["chunk_id"] for r in registros] == [f"largo:1:parrafos:{i:03d}" for i in range(len(registros))]


def test_documentos_validados_contra_el_manifiesto(tmp_path):
    (tmp_path / "manifiesto.json").write_text(json.dumps({"a.md": {"version": "1"}}), encoding="utf-8")
    (tmp_path / "a.md").write_text("# Título\r\n\r\n\r\n\r\nNo se acepta  nunca.\n", encoding="utf-8")
    documento = cc.cargar_documentos(tmp_path)[0]
    assert documento["texto"] == "# Título\n\nNo se acepta nunca." and documento["version"] == "1"
    (tmp_path / "b.md").write_text("# Otro\n", encoding="utf-8")
    with pytest.raises(cc.ErrorCarga, match="manifiesto"):
        cc.cargar_documentos(tmp_path)
    (tmp_path / "b.md").unlink()
    (tmp_path / "a.md").write_text("Sin título\n", encoding="utf-8")
    with pytest.raises(cc.ErrorCarga, match="título"):
        cc.cargar_documentos(tmp_path)


def test_carga_idempotente_con_el_usuario_como_dueno():
    cliente, registros = ClienteFalso(), registros_de_prueba()
    configuracion = cc.configuracion_indice(128, "1")
    primera = cc.cargar(cliente, "usuario-1", "corpus-x", configuracion, registros, codificar_falso)
    assert primera["filas"] == 60 and primera["modo"].startswith("cargado con upsert")
    assert cliente.lotes == [(50, "owner_id,corpus_id,chunk_id"), (10, "owner_id,corpus_id,chunk_id")]
    fila = next(iter(cliente.filas.values()))
    assert fila["owner_id"] == "usuario-1" and "texto" not in fila["metadata"] and "chunk_id" not in fila["metadata"] and len(fila["embedding"]) == 384
    segunda = cc.cargar(cliente, "usuario-1", "corpus-x", configuracion, registros, codificar_falso)
    assert segunda["modo"] == "ya estaba completo; no se reescribió" and len(cliente.lotes) == 2
    cc.cargar(cliente, "usuario-1", "corpus-x", configuracion, registros, codificar_falso, forzar=True)
    assert len(cliente.lotes) == 4
    nombre, parametros = cliente.llamadas_rpc[-1]
    assert nombre == "analizador_buscar_fragmentos_autorizado" and parametros["p_propietario_id"] == "usuario-1"
    assert parametros["p_modelo"] == rc.MODELO_EMBEDDINGS and parametros["p_revision"] == rc.REVISION_EMBEDDINGS


def test_carga_falla_si_las_filas_no_coinciden():
    cliente = ClienteFalso()
    cliente.perdidas = 1
    with pytest.raises(cc.ErrorCarga, match="filas"):
        cc.cargar(cliente, "usuario-1", "corpus-x", cc.configuracion_indice(128, "1"), registros_de_prueba(5), codificar_falso)


def test_carga_falla_si_la_busqueda_remota_no_coincide_con_la_local():
    cliente = ClienteFalso(primero="otro:fragmento")
    with pytest.raises(cc.ErrorCarga, match="búsqueda remota"):
        cc.cargar(cliente, "usuario-1", "corpus-x", cc.configuracion_indice(128, "1"), registros_de_prueba(5), codificar_falso)


def test_identificador_cambia_con_el_contenido():
    configuracion = cc.configuracion_indice(128, "1")
    registros = registros_de_prueba(3)
    otro = [dict(registros[0], texto="cambiado")] + registros[1:]
    assert cc.identificador_corpus(configuracion, registros) != cc.identificador_corpus(configuracion, otro)
    assert cc.identificador_corpus(configuracion, registros).startswith(cc.CORPUS_BASE + "-")


def test_main_imprime_identificadores_sin_secretos(monkeypatch, capsys):
    cliente = ClienteFalso()
    registros = registros_de_prueba(4)

    class AutenticacionFalsa:
        def __init__(self, configuracion):
            self.cerradas = []

        def iniciar_sesion(self, correo, clave):
            assert clave == "clave-muy-secreta"
            return al.Sesion("acceso-secreto", "renovacion-secreta", 0.0, "11111111-2222-3333-4444-555555555555", correo)

        def cerrar_sesion(self, acceso, renovacion):
            self.cerradas.append(acceso)

    monkeypatch.setattr("sistema.cargar_entorno", lambda: {"SUPABASE_URL": "https://p.supabase.co", "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_privada"})
    monkeypatch.setattr(cc.descargar_modelos, "asegurar", lambda: None)
    monkeypatch.setattr(cc, "preparar", lambda: ("corpus-x", cc.configuracion_indice(128, "1"), registros))
    monkeypatch.setattr(cc, "credenciales", lambda entorno: ("dueno@prueba.local", "clave-muy-secreta"))
    monkeypatch.setattr(cc.al, "Autenticacion", AutenticacionFalsa)
    monkeypatch.setattr(cc.al, "crear_cliente", lambda configuracion, token: cliente)
    monkeypatch.setattr(cc.rc, "ModeloEmbeddings", lambda carpeta, tokenizador: SimpleNamespace(codificar=codificar_falso))
    monkeypatch.setattr(cc.rc, "TokenizadorXLMR", lambda ruta: None)
    assert cc.main([]) == 0
    salida = capsys.readouterr()
    texto = salida.out + salida.err
    assert "CORPUS_ID=corpus-x" in texto and "CORPUS_PROPIETARIO_ID=11111111-2222-3333-4444-555555555555" in texto
    for secreto in ("clave-muy-secreta", "acceso-secreto", "renovacion-secreta", "sb_publishable_privada"):
        assert secreto not in texto


def test_sin_claves_administrativas():
    texto = Path(cc.__file__).read_text(encoding="utf-8").lower()
    assert "service_role" not in texto and "sb_secret" not in texto and "admin" not in texto
