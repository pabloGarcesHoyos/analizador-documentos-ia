import hashlib
import sys
import urllib.request
from pathlib import Path

CARPETA = Path(__file__).resolve().parent / "modelos"

ARCHIVOS = {
    "embeddings": ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "e8f8c211226b894fcb81acc59f3b34ba3efd5f42", {
        "sentencepiece.bpe.model": ("sha256", "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865", 5069051),
        "1_Pooling/config.json": ("git", "d1514c3162bbe87b343f565fadc62e6c06f04f03", 190),
        "sentence_bert_config.json": ("git", "5fd10429389515d3e5cccdeda08cae5fea1ae82e", 53),
        "onnx/model_qint8_arm64.onnx": ("sha256", "783fea82d71a58179b830a4dbd2d58447e640609e98eedf9ffa12622d375a672", 118412398),
    }),
    "reranker": ("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", "1427fd652930e4ba29e8149678df786c240d8825", {
        "config.json": ("git", "43ac97f1bef372d4f1d30a32f9a84baffcf6575d", 891),
        "onnx/model_qint8_arm64.onnx": ("sha256", "1825907d6c1a9001ff78124780bbde20a614a8c3df3b63409cf3c72c6fe5c8b4", 118620017),
    }),
}


def huella(tipo, ruta):
    datos = ruta.read_bytes()
    if tipo == "git":
        return hashlib.sha1(b"blob %d\0" % len(datos) + datos).hexdigest()
    return hashlib.sha256(datos).hexdigest()


def faltantes(carpeta=CARPETA):
    return [(c, n) for c, (_, _, archivos) in ARCHIVOS.items() for n, (_, _, tamano) in archivos.items()
            if not (carpeta / c / n).is_file() or (carpeta / c / n).stat().st_size != tamano]


def descargar(carpeta=CARPETA):
    for subcarpeta, (repositorio, revision, archivos) in ARCHIVOS.items():
        for nombre, (tipo, esperado, _) in archivos.items():
            destino = carpeta / subcarpeta / nombre
            if destino.is_file() and huella(tipo, destino) == esperado:
                continue
            destino.parent.mkdir(parents=True, exist_ok=True)
            temporal = destino.with_name(destino.name + ".parcial")
            urllib.request.urlretrieve(f"https://huggingface.co/{repositorio}/resolve/{revision}/{nombre}", temporal)
            if huella(tipo, temporal) != esperado:
                temporal.unlink()
                raise RuntimeError(f"La huella de {subcarpeta}/{nombre} no coincide con la revision fijada.")
            temporal.replace(destino)
            print(f"descargado {subcarpeta}/{nombre}")


def asegurar(carpeta=CARPETA):
    if faltantes(carpeta):
        descargar(carpeta)


if __name__ == "__main__":
    try:
        descargar()
    except (OSError, RuntimeError) as error:
        sys.exit(str(error))
    print("modelos verificados")
