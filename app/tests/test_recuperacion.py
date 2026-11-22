import json
from pathlib import Path

import numpy as np
import pytest

import descargar_modelos
import recuperacion as rc

DATOS = Path(__file__).resolve().parent / "datos"
FRAGMENTOS = json.loads((DATOS / "fragmentos.json").read_text(encoding="utf-8"))
CASOS = json.loads((DATOS / "casos_corte2.json").read_text(encoding="utf-8"))
VECTORES = np.load(DATOS / "vectores_corpus.npy")
OPCIONES = ("A_semantica", "B_hibrida_RRF", "C_hibrida_reranking")
CORTE2 = {
    "desarrollo": {"A_semantica": (0.875, 0.875, 0.875), "B_hibrida_RRF": (0.812, 0.792, 0.812), "C_hibrida_reranking": (0.938, 0.938, 0.938)},
    "reserva": {"A_semantica": (0.75, 0.75, 0.75), "B_hibrida_RRF": (1.0, 1.0, 1.0), "C_hibrida_reranking": (1.0, 1.0, 1.0)},
}

requiere_modelos = pytest.mark.skipif(bool(descargar_modelos.faltantes()), reason="Faltan los modelos: ejecuta python app/descargar_modelos.py")


class FuenteLocal:
    def __init__(self, fragmentos=FRAGMENTOS, vectores=VECTORES):
        self._fragmentos = fragmentos
        self._vectores = vectores
        self.consultas_semanticas = 0

    def fragmentos(self):
        return [dict(f) for f in self._fragmentos]

    def semanticos(self, vector, cantidad):
        self.consultas_semanticas += 1
        similitud = self._vectores @ np.asarray(vector, dtype=np.float32)
        orden = sorted(range(len(self._fragmentos)), key=lambda i: (-similitud[i], self._fragmentos[i]["chunk_id"]))[:cantidad]
        return [dict(self._fragmentos[i], similitud=float(similitud[i])) for i in orden]


def metricas(seleccion, unidades):
    relevantes = set().union(*map(set, unidades.values()))
    primera = next((i for i, x in enumerate(seleccion, 1) if x in relevantes), None)
    return (sum(bool(set(v) & set(seleccion)) for v in unidades.values()) / len(unidades),
            1 / primera if primera else 0.0,
            len(set(seleccion) & relevantes) / len(relevantes))


def agregado(selecciones):
    resultado = {}
    for grupo in ("desarrollo", "reserva"):
        casos = [c for c in CASOS if c["grupo"] == grupo]
        resultado[grupo] = {o: tuple(round(float(np.mean([metricas(selecciones[c["id"]][o], c["unidades"])[i] for c in casos])), 3) for i in range(3))
                            for o in OPCIONES}
    return resultado


@pytest.fixture(scope="module")
def recuperador_c():
    return rc.Recuperador("C_DEMANDA")


@requiere_modelos
def test_metricas_agregadas_del_corte2_con_onnx(recuperador_c):
    fuente = FuenteLocal()
    obtenidas = {c["id"]: recuperador_c.evaluar(c["pregunta"], fuente) for c in CASOS}
    referencia = {c["id"]: c["seleccion_corte2"] for c in CASOS}
    assert agregado(referencia) == CORTE2
    assert agregado(obtenidas) == CORTE2
    iguales = sum(obtenidas[c["id"]][o] == c["seleccion_corte2"][o] for c in CASOS for o in OPCIONES)
    assert iguales >= 42


@requiere_modelos
def test_modos_entregan_su_configuracion(recuperador_c):
    fuente = FuenteLocal()
    caso = next(c for c in CASOS if c["id"] == "D5")
    evaluado = recuperador_c.evaluar(caso["pregunta"], fuente)
    resultado_c = recuperador_c.recuperar(caso["pregunta"], fuente)
    assert resultado_c.modo == "C_DEMANDA" and [p.chunk_id for p in resultado_c.seleccion] == evaluado["C_hibrida_reranking"]
    assert all(p.puntaje_reranker is not None for p in resultado_c.candidatos)
    resultado_b = rc.Recuperador("B").recuperar(caso["pregunta"], fuente)
    assert resultado_b.modo == "B" and [p.chunk_id for p in resultado_b.seleccion] == evaluado["B_hibrida_RRF"]
    assert all(p.puntaje_reranker is None for p in resultado_b.candidatos)
    assert len(resultado_c.seleccion) == rc.K and len(resultado_c.candidatos) <= rc.M


@requiere_modelos
def test_c_demanda_no_deja_modelos_residentes_y_b_si(recuperador_c):
    assert recuperador_c._embeddings is None
    assert isinstance(rc.Recuperador("B")._embeddings, rc.ModeloEmbeddings)


@requiere_modelos
def test_sin_fragmentos_visibles_es_sin_acceso_y_no_busca(recuperador_c):
    fuente = FuenteLocal(fragmentos=[], vectores=VECTORES[:0])
    with pytest.raises(rc.SinAccesoCorpus):
        recuperador_c.recuperar("¿Qué requisitos tiene una factura?", fuente)
    assert fuente.consultas_semanticas == 0


@requiere_modelos
def test_corpus_cambiado_durante_la_consulta(recuperador_c):
    class FuenteAlterada(FuenteLocal):
        def semanticos(self, vector, cantidad):
            return [dict(f, content=f["content"] + " alterado") for f in super().semanticos(vector, cantidad)]
    with pytest.raises(rc.ErrorRecuperacion, match="cambió"):
        recuperador_c.recuperar("¿Qué requisitos tiene una factura?", FuenteAlterada())


@requiere_modelos
def test_consulta_vacia(recuperador_c):
    with pytest.raises(rc.ErrorRecuperacion):
        recuperador_c.recuperar("   ", FuenteLocal())


@requiere_modelos
def test_tokenizador_xlmr_plantillas_y_truncado(recuperador_c):
    tokenizador = recuperador_c.tokenizador
    uno = tokenizador.uno("Factura sin NIT", 128)
    assert uno[0] == 0 and uno[-1] == 2 and 3 not in uno[1:-1]
    assert len(tokenizador.uno("palabra " * 400, 128)) == 128
    par = tokenizador.par("¿Pregunta?", "Texto del fragmento", 256)
    assert par[0] == 0 and par[-1] == 2 and par.count(2) == 3
    assert len(tokenizador.par("a " * 300, "b " * 300, 256)) == 256


@requiere_modelos
def test_embeddings_normalizados_y_deterministas(recuperador_c):
    modelo = rc.ModeloEmbeddings(rc.CARPETA_MODELOS, recuperador_c.tokenizador)
    a = modelo.codificar("¿Con qué tasa se registra una factura en dólares?")
    assert a.shape == (384,) and abs(float(np.linalg.norm(a)) - 1) < 1e-5
    assert np.array_equal(a, modelo.codificar("¿Con qué tasa se registra una factura en dólares?"))


def test_rrf_reproduce_el_ejemplo_de_la_clase_09():
    fusion = rc.fusionar_rrf(list("ABC"), list("CAD"))
    assert [f[0] for f in fusion] == list("ACBD")
    assert fusion[0][3] == pytest.approx(1 / 61 + 1 / 62)
    assert fusion[0][1:3] == (1, 2) and fusion[3][1:3] == (None, 3)


def test_rrf_rechaza_identificadores_repetidos():
    with pytest.raises(rc.ErrorRecuperacion):
        rc.fusionar_rrf(["A", "A"], ["B"])


def test_tokenizacion_bm25_sin_tildes_y_con_codigos():
    assert rc.tokenizar_bm25("La cédula DOC-1001 NO está vencida") == ["la", "cedula", "doc-1001", "no", "esta", "vencida"]


def test_modo_invalido():
    with pytest.raises(rc.ErrorRecuperacion):
        rc.Recuperador("C")


def test_fuente_supabase_usa_la_funcion_autorizada_y_filtra_el_corpus():
    llamadas = []

    class Consulta:
        def __init__(self, nombre):
            llamadas.append(("tabla", nombre))

        def __getattr__(self, metodo):
            def registrar(*argumentos, **opciones):
                llamadas.append((metodo, argumentos))
                return self
            return registrar

        def execute(self):
            return type("R", (), {"data": []})()

    class Cliente:
        def table(self, nombre):
            return Consulta(nombre)

        def rpc(self, nombre, parametros):
            llamadas.append(("rpc", nombre, parametros))
            return Consulta("rpc")

    fuente = rc.FuenteSupabase(Cliente(), "propietario", "corpus")
    fuente.fragmentos()
    fuente.semanticos([0.1] * 384, 10)
    assert ("eq", ("owner_id", "propietario")) in llamadas and ("eq", ("corpus_id", "corpus")) in llamadas
    rpc = next(x for x in llamadas if x[0] == "rpc")
    assert rpc[1] == "analizador_buscar_fragmentos_autorizado"
    assert rpc[2]["p_propietario_id"] == "propietario" and rpc[2]["match_count"] == 10 and len(rpc[2]["query_embedding"]) == 384
