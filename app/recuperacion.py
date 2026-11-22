import gc
import hashlib
import json
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import onnxruntime as ort
import sentencepiece as spm
from rank_bm25 import BM25Okapi

MODELO_EMBEDDINGS = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION_EMBEDDINGS = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
MODELO_RERANKER = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
REVISION_RERANKER = "1427fd652930e4ba29e8149678df786c240d8825"
VARIANTE_ONNX = "qint8_arm64"
FUNCION_BUSQUEDA = "analizador_buscar_fragmentos_autorizado"
K, M, C_RRF = 3, 10, 60
BM25_K1, BM25_B, BM25_EPSILON = 1.5, 0.75, 0.25
MAXIMO_RERANKER = 256
MAXIMO_FRAGMENTOS = 500
MODOS = ("C_DEMANDA", "B")
CARPETA_MODELOS = Path(__file__).resolve().parent / "modelos"
INICIO, FIN, DESCONOCIDO = 0, 2, 3


class ErrorRecuperacion(Exception):
    pass


class SinAccesoCorpus(ErrorRecuperacion):
    pass


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.casefold())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).split())


def tokenizar_bm25(texto: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:[-_][^\W_]+)*", normalizar(texto))


class TokenizadorXLMR:
    def __init__(self, ruta: Path):
        self.sp = spm.SentencePieceProcessor(model_file=str(ruta))

    def _ids(self, texto: str) -> list[int]:
        return [DESCONOCIDO if i == 0 else i + 1 for i in self.sp.encode(texto, out_type=int)]

    def uno(self, texto: str, maximo: int) -> list[int]:
        return [INICIO, *self._ids(texto)[: maximo - 2], FIN]

    def par(self, a: str, b: str, maximo: int) -> list[int]:
        x, y = self._ids(a), self._ids(b)
        while len(x) + len(y) > maximo - 4:
            if len(x) > len(y):
                x.pop()
            else:
                y.pop()
        return [INICIO, *x, FIN, FIN, *y, FIN]


def _sesion(ruta: Path) -> ort.InferenceSession:
    opciones = ort.SessionOptions()
    opciones.intra_op_num_threads = 1
    opciones.inter_op_num_threads = 1
    opciones.enable_cpu_mem_arena = False
    opciones.enable_mem_pattern = False
    opciones.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    return ort.InferenceSession(str(ruta), sess_options=opciones, providers=["CPUExecutionProvider"])


def _entradas(sesion: ort.InferenceSession, ids: list[int]) -> dict:
    matriz = np.array([ids], dtype=np.int64)
    valores = {"input_ids": matriz, "attention_mask": np.ones_like(matriz), "token_type_ids": np.zeros_like(matriz)}
    return {e.name: valores[e.name] for e in sesion.get_inputs()}


class ModeloEmbeddings:
    def __init__(self, carpeta: Path, tokenizador: TokenizadorXLMR):
        base = carpeta / "embeddings"
        if not json.loads((base / "1_Pooling/config.json").read_text())["pooling_mode_mean_tokens"]:
            raise ErrorRecuperacion("El modelo de embeddings debe usar mean pooling.")
        self.maximo = json.loads((base / "sentence_bert_config.json").read_text())["max_seq_length"]
        self.tokenizador = tokenizador
        self.sesion = _sesion(base / f"onnx/model_{VARIANTE_ONNX}.onnx")

    def codificar(self, texto: str) -> np.ndarray:
        tokens = self.sesion.run(None, _entradas(self.sesion, self.tokenizador.uno(texto, self.maximo)))[0][0]
        media = tokens.mean(axis=0)
        return (media / max(float(np.linalg.norm(media)), 1e-12)).astype(np.float32)


class ModeloReranker:
    def __init__(self, carpeta: Path, tokenizador: TokenizadorXLMR):
        self.tokenizador = tokenizador
        self.sesion = _sesion(carpeta / f"reranker/onnx/model_{VARIANTE_ONNX}.onnx")

    def puntuar(self, consulta: str, textos: list[str]) -> list[float]:
        return [float(self.sesion.run(None, _entradas(self.sesion, self.tokenizador.par(consulta, t, MAXIMO_RERANKER)))[0].reshape(-1)[0])
                for t in textos]


class FuenteCorpus(Protocol):
    def fragmentos(self) -> list[dict]:
        ...

    def semanticos(self, vector: list[float], cantidad: int) -> list[dict]:
        ...


class FuenteSupabase:
    def __init__(self, cliente: Any, propietario_id: str, corpus_id: str):
        self.cliente = cliente
        self.propietario_id = propietario_id
        self.corpus_id = corpus_id

    def fragmentos(self) -> list[dict]:
        return (self.cliente.table("analizador_fragmentos").select("chunk_id,content,metadata")
                .eq("owner_id", self.propietario_id).eq("corpus_id", self.corpus_id)
                .eq("configuracion->>modelo", MODELO_EMBEDDINGS).eq("configuracion->>revision", REVISION_EMBEDDINGS)
                .order("chunk_id").limit(MAXIMO_FRAGMENTOS + 1).execute().data or [])

    def semanticos(self, vector: list[float], cantidad: int) -> list[dict]:
        return self.cliente.rpc(FUNCION_BUSQUEDA, {
            "query_embedding": vector, "p_propietario_id": self.propietario_id, "p_corpus_id": self.corpus_id,
            "p_modelo": MODELO_EMBEDDINGS, "p_revision": REVISION_EMBEDDINGS, "match_count": cantidad}).execute().data or []


@dataclass
class Pasaje:
    chunk_id: str
    texto: str
    metadata: dict
    posicion_semantica: int | None = None
    posicion_bm25: int | None = None
    puntaje_rrf: float = 0.0
    puntaje_reranker: float | None = None
    similitud: float | None = None

    def como_dict(self) -> dict:
        return {"chunk_id": self.chunk_id, "texto": self.texto, "source": self.metadata.get("source"),
                "section": self.metadata.get("section"), "version": self.metadata.get("version"),
                "posicion_semantica": self.posicion_semantica, "posicion_bm25": self.posicion_bm25,
                "puntaje_rrf": round(self.puntaje_rrf, 6), "puntaje_reranker": self.puntaje_reranker,
                "similitud": self.similitud}


@dataclass
class ResultadoRecuperacion:
    modo: str
    seleccion: list[Pasaje]
    candidatos: list[Pasaje]
    tiempos_ms: dict = field(default_factory=dict)


def fusionar_rrf(semanticos: list[str], lexicos: list[str], c: int = C_RRF) -> list[tuple[str, int | None, int | None, float]]:
    for lista in (semanticos, lexicos):
        if len(set(lista)) != len(lista):
            raise ErrorRecuperacion("Un ranking contiene identificadores repetidos.")
    posiciones = {}
    for nombre, lista in (("semantica", semanticos), ("bm25", lexicos)):
        for posicion, chunk_id in enumerate(lista, 1):
            posiciones.setdefault(chunk_id, {"semantica": None, "bm25": None})[nombre] = posicion
    puntajes = {k: sum(1 / (c + p) for p in v.values() if p) for k, v in posiciones.items()}
    orden = sorted(puntajes, key=lambda k: (-puntajes[k], k))
    return [(k, posiciones[k]["semantica"], posiciones[k]["bm25"], puntajes[k]) for k in orden]


class _IndiceLexico:
    def __init__(self, fragmentos: list[dict]):
        self.ids = [f["chunk_id"] for f in fragmentos]
        self.tokens = [tokenizar_bm25(f["content"]) for f in fragmentos]
        self.bm25 = BM25Okapi(self.tokens, k1=BM25_K1, b=BM25_B, epsilon=BM25_EPSILON)

    def buscar(self, consulta: str) -> list[str]:
        terminos = tokenizar_bm25(consulta)
        puntajes = self.bm25.get_scores(terminos)
        coincidencias = [i for i, palabras in enumerate(self.tokens) if set(terminos) & set(palabras)]
        return [self.ids[i] for i in sorted(coincidencias, key=lambda i: (-puntajes[i], self.ids[i]))[:M]]


def _huella_corpus(fragmentos: list[dict]) -> str:
    return hashlib.sha256(json.dumps([[f["chunk_id"], f["content"]] for f in fragmentos], ensure_ascii=False).encode()).hexdigest()


class Recuperador:
    def __init__(self, modo: str = "C_DEMANDA", carpeta: Path = CARPETA_MODELOS):
        modo = (modo or "C_DEMANDA").upper()
        if modo not in MODOS:
            raise ErrorRecuperacion("RECUPERACION debe ser C_DEMANDA o B.")
        self.modo = modo
        self.carpeta = carpeta
        self.tokenizador = TokenizadorXLMR(carpeta / "embeddings/sentencepiece.bpe.model")
        self._embeddings = ModeloEmbeddings(carpeta, self.tokenizador) if modo == "B" else None
        self._candado = threading.Lock()
        self._indices: dict[str, _IndiceLexico] = {}

    def _vector(self, consulta: str) -> np.ndarray:
        if self._embeddings is not None:
            return self._embeddings.codificar(consulta)
        modelo = ModeloEmbeddings(self.carpeta, self.tokenizador)
        try:
            return modelo.codificar(consulta)
        finally:
            del modelo
            gc.collect()

    def _reordenar(self, consulta: str, textos: list[str]) -> list[float]:
        modelo = ModeloReranker(self.carpeta, self.tokenizador)
        try:
            return modelo.puntuar(consulta, textos)
        finally:
            del modelo
            gc.collect()

    def _indice(self, fragmentos: list[dict]) -> _IndiceLexico:
        clave = _huella_corpus(fragmentos)
        if clave not in self._indices:
            self._indices = {clave: _IndiceLexico(fragmentos)}
        return self._indices[clave]

    def _recorrer(self, consulta: str, fuente: FuenteCorpus, con_reranker: bool) -> dict:
        tiempos = {}
        inicio = time.perf_counter()
        fragmentos = fuente.fragmentos()
        if not fragmentos:
            raise SinAccesoCorpus("El usuario no tiene acceso al corpus autorizado o el corpus está vacío.")
        if len(fragmentos) > MAXIMO_FRAGMENTOS:
            raise ErrorRecuperacion("El corpus supera el máximo de fragmentos previsto para BM25 en memoria.")
        por_id = {f["chunk_id"]: f for f in fragmentos}
        tiempos["lectura_corpus"] = (time.perf_counter() - inicio) * 1000
        inicio = time.perf_counter()
        vector = self._vector(consulta)
        tiempos["embedding"] = (time.perf_counter() - inicio) * 1000
        inicio = time.perf_counter()
        semanticos = fuente.semanticos([float(x) for x in vector], M)
        tiempos["busqueda_semantica"] = (time.perf_counter() - inicio) * 1000
        if not semanticos:
            raise ErrorRecuperacion("La búsqueda semántica no devolvió candidatos.")
        for candidato in semanticos:
            if candidato["chunk_id"] not in por_id or candidato["content"] != por_id[candidato["chunk_id"]]["content"]:
                raise ErrorRecuperacion("El corpus cambió durante la consulta.")
        similitud = {c["chunk_id"]: c.get("similitud") for c in semanticos}
        inicio = time.perf_counter()
        lexicos = self._indice(fragmentos).buscar(consulta)
        fusion = fusionar_rrf([c["chunk_id"] for c in semanticos], lexicos)
        tiempos["bm25_rrf"] = (time.perf_counter() - inicio) * 1000
        hibridos = [Pasaje(k, por_id[k]["content"], por_id[k].get("metadata") or {}, ps, pb, rrf, None, similitud.get(k))
                    for k, ps, pb, rrf in fusion[:M]]
        reordenados = None
        if con_reranker:
            inicio = time.perf_counter()
            puntajes = self._reordenar(consulta, [p.texto for p in hibridos])
            tiempos["reranker"] = (time.perf_counter() - inicio) * 1000
            for pasaje, puntaje in zip(hibridos, puntajes):
                pasaje.puntaje_reranker = round(puntaje, 6)
            reordenados = [hibridos[j] for j in sorted(range(len(hibridos)), key=lambda j: (-puntajes[j], hibridos[j].chunk_id))]
        return {"semanticos": [c["chunk_id"] for c in semanticos], "hibridos": hibridos, "reordenados": reordenados,
                "tiempos": {k: round(v, 1) for k, v in tiempos.items()}}

    def recuperar(self, consulta: str, fuente: FuenteCorpus) -> ResultadoRecuperacion:
        if not isinstance(consulta, str) or not consulta.strip():
            raise ErrorRecuperacion("La consulta está vacía.")
        with self._candado:
            recorrido = self._recorrer(consulta.strip(), fuente, self.modo == "C_DEMANDA")
        candidatos = recorrido["reordenados"] if self.modo == "C_DEMANDA" else recorrido["hibridos"]
        return ResultadoRecuperacion(self.modo, candidatos[:K], candidatos, recorrido["tiempos"])

    def evaluar(self, consulta: str, fuente: FuenteCorpus) -> dict[str, list[str]]:
        with self._candado:
            recorrido = self._recorrer(consulta.strip(), fuente, True)
        return {"A_semantica": recorrido["semanticos"][:K],
                "B_hibrida_RRF": [p.chunk_id for p in recorrido["hibridos"][:K]],
                "C_hibrida_reranking": [p.chunk_id for p in recorrido["reordenados"][:K]]}
