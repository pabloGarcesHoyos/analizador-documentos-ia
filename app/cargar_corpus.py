import argparse
import getpass
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np

import almacenamiento as al
import descargar_modelos
import recuperacion as rc

CARPETA_APP = Path(__file__).resolve().parent
CARPETA_CORPUS = CARPETA_APP / "corpus"
CORPUS_BASE = "analizador_documental_v2"
ESTRATEGIA = "parrafos"
MAX_TOKENS, SOLAPAMIENTO = 120, 20
VENTANA_TOKENS, SOLAPAMIENTO_VENTANA = 60, 15
TAMANO_LOTE = 50
PREGUNTA_VERIFICACION = "¿Qué requisitos tiene una factura para contabilizarse?"
NEGACIONES = ("no ", "nunca", "ni ")


class ErrorCarga(Exception):
    pass


def limpiar(texto: str) -> str:
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"[ ]+\n", "\n", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def cargar_documentos(carpeta: Path = CARPETA_CORPUS) -> list[dict]:
    manifiesto = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
    documentos = []
    for ruta in sorted(carpeta.glob("*.md")):
        if ruta.name not in manifiesto:
            raise ErrorCarga(f"{ruta.name} no está en el manifiesto.")
        normalizado = ruta.read_bytes().decode("utf-8").replace("\r\n", "\n")
        limpio = limpiar(normalizado)
        if not limpio.startswith("# "):
            raise ErrorCarga(f"{ruta.name} debe comenzar con un título '# '.")
        perdidas = [p for p in NEGACIONES if normalizado.lower().count(p) != limpio.lower().count(p)]
        if perdidas:
            raise ErrorCarga(f"La limpieza alteró negaciones en {ruta.name}: {perdidas}")
        documentos.append({"document_id": ruta.stem, "source": ruta.name, "title": limpio.splitlines()[0][2:].strip(),
                           "version": manifiesto[ruta.name]["version"], "source_hash": hashlib.sha256(normalizado.encode("utf-8")).hexdigest(),
                           "texto": limpio})
    if not documentos:
        raise ErrorCarga("No hay documentos en la carpeta del corpus.")
    return documentos


def secciones(documento: dict) -> list[tuple[str, str]]:
    cuerpo = documento["texto"].split("\n", 1)[1] if "\n" in documento["texto"] else ""
    partes = re.split(r"(?m)^## ", cuerpo)
    salida = [("Presentación", partes[0].strip())] if partes[0].strip() else []
    for bloque in partes[1:]:
        titulo, _, contenido = bloque.partition("\n")
        if contenido.strip():
            salida.append((titulo.strip(), contenido.strip()))
    return salida


def ventanas(tokenizador: rc.TokenizadorXLMR, texto: str, limite: int, solape: int):
    desplazamientos = tokenizador.desplazamientos(texto)
    if limite <= solape:
        raise ErrorCarga("El encabezado deja muy poco espacio para el contenido.")
    for inicio in range(0, len(desplazamientos), limite - solape):
        fin = min(inicio + limite, len(desplazamientos))
        yield texto[desplazamientos[inicio][0]:desplazamientos[fin - 1][1]].strip()
        if fin == len(desplazamientos):
            break


def trozos_que_caben(tokenizador: rc.TokenizadorXLMR, encabezado: str, texto: str, limite: int, solape: int, tope: int) -> list[str]:
    while limite > solape + 4:
        trozos = [t for t in ventanas(tokenizador, texto, limite, solape) if t]
        if all(tokenizador.contar(encabezado + t) <= tope for t in trozos):
            return trozos
        limite -= 4
    raise ErrorCarga("No fue posible dividir el texto dentro del límite del modelo.")


def fragmentar(documentos: list[dict], tokenizador: rc.TokenizadorXLMR, tope: int) -> list[dict]:
    registros = []
    for documento in documentos:
        numero_fragmento = 0
        for numero, (seccion, contenido) in enumerate(secciones(documento), 1):
            encabezado = f"{documento['title']} / {seccion}\n"
            piezas = []
            for parrafo in re.split(r"\n\s*\n", contenido):
                parrafo = parrafo.strip()
                if tokenizador.contar(encabezado + parrafo) <= tope:
                    piezas.append((parrafo, False))
                else:
                    limite = tope - tokenizador.contar(encabezado) - 2
                    piezas += [(t, True) for t in trozos_que_caben(tokenizador, encabezado, parrafo, limite, SOLAPAMIENTO, tope)]
            for texto, dividido in piezas:
                registros.append({
                    **{k: documento[k] for k in ("document_id", "source", "title", "version", "source_hash")},
                    "chunk_id": f"{documento['document_id']}:{documento['version']}:{ESTRATEGIA}:{numero_fragmento:03d}",
                    "section": seccion, "section_number": numero, "estrategia": ESTRATEGIA, "dividido": dividido,
                    "tokens": tokenizador.contar(encabezado + texto), "texto": encabezado + texto})
                numero_fragmento += 1
    return registros


def configuracion_indice(max_seq_length: int, version_corpus: str) -> dict:
    return {"modelo": rc.MODELO_EMBEDDINGS, "revision": rc.REVISION_EMBEDDINGS, "estrategia": ESTRATEGIA, "max_tokens": MAX_TOKENS,
            "solapamiento": SOLAPAMIENTO, "ventana_tokens": VENTANA_TOKENS, "solapamiento_ventana": SOLAPAMIENTO_VENTANA,
            "normalizados": True, "similitud": "coseno", "max_seq_length": max_seq_length, "version_corpus": version_corpus}


def identificador_corpus(configuracion: dict, registros: list[dict]) -> str:
    huella = hashlib.sha256(json.dumps({"configuracion": configuracion, "registros": registros}, sort_keys=True, ensure_ascii=False)
                            .encode("utf-8")).hexdigest()[:12]
    return f"{CORPUS_BASE}-{huella}"


def preparar(carpeta_corpus: Path = CARPETA_CORPUS, carpeta_modelos: Path = rc.CARPETA_MODELOS) -> tuple[str, dict, list[dict]]:
    documentos = cargar_documentos(carpeta_corpus)
    versiones = {d["version"] for d in documentos}
    if len(versiones) != 1:
        raise ErrorCarga(f"Los documentos tienen versiones distintas: {sorted(versiones)}")
    tokenizador = rc.TokenizadorXLMR(carpeta_modelos / "embeddings/sentencepiece.bpe.model")
    max_seq_length = json.loads((carpeta_modelos / "embeddings/sentence_bert_config.json").read_text())["max_seq_length"]
    registros = fragmentar(documentos, tokenizador, min(MAX_TOKENS, max_seq_length))
    configuracion = configuracion_indice(max_seq_length, versiones.pop())
    return identificador_corpus(configuracion, registros), configuracion, registros


def filas_para_subir(registros: list[dict], vectores: np.ndarray, usuario_id: str, corpus_id: str, configuracion: dict) -> list[dict]:
    return [{"owner_id": usuario_id, "corpus_id": corpus_id, "chunk_id": r["chunk_id"], "content": r["texto"],
             "metadata": {k: v for k, v in r.items() if k not in ("texto", "chunk_id")}, "configuracion": configuracion,
             "embedding": [float(x) for x in vectores[i]]} for i, r in enumerate(registros)]


def contar_filas(cliente: Any, usuario_id: str, corpus_id: str) -> int:
    respuesta = (cliente.table("analizador_fragmentos").select("chunk_id", count="exact").eq("owner_id", usuario_id)
                 .eq("corpus_id", corpus_id).limit(1).execute())
    return int(respuesta.count or 0)


def subir(cliente: Any, filas: list[dict]) -> None:
    for inicio in range(0, len(filas), TAMANO_LOTE):
        cliente.table("analizador_fragmentos").upsert(filas[inicio:inicio + TAMANO_LOTE], on_conflict="owner_id,corpus_id,chunk_id").execute()


def verificar_busqueda(cliente: Any, usuario_id: str, corpus_id: str, registros: list[dict], vectores: np.ndarray, consulta: np.ndarray) -> str:
    local = registros[int(np.argmax(vectores @ consulta))]["chunk_id"]
    remoto = cliente.rpc("analizador_buscar_fragmentos_autorizado", {
        "query_embedding": [float(x) for x in consulta], "p_propietario_id": usuario_id, "p_corpus_id": corpus_id,
        "p_modelo": rc.MODELO_EMBEDDINGS, "p_revision": rc.REVISION_EMBEDDINGS, "match_count": 3}).execute().data or []
    if not remoto or remoto[0]["chunk_id"] != local:
        raise ErrorCarga("La búsqueda remota no devuelve el mismo primer resultado que la búsqueda exacta local.")
    return local


def cargar(cliente: Any, usuario_id: str, corpus_id: str, configuracion: dict, registros: list[dict], codificar, forzar: bool = False) -> dict:
    vectores = np.array([codificar(r["texto"]) for r in registros], dtype=np.float32)
    existentes = contar_filas(cliente, usuario_id, corpus_id)
    if existentes == len(registros) and not forzar:
        modo = "ya estaba completo; no se reescribió"
    else:
        subir(cliente, filas_para_subir(registros, vectores, usuario_id, corpus_id, configuracion))
        modo = f"cargado con upsert ({len(registros)} filas; antes había {existentes})"
    finales = contar_filas(cliente, usuario_id, corpus_id)
    if finales != len(registros):
        raise ErrorCarga(f"Supabase tiene {finales} filas y el índice local {len(registros)}.")
    primero = verificar_busqueda(cliente, usuario_id, corpus_id, registros, vectores, codificar(PREGUNTA_VERIFICACION))
    return {"modo": modo, "filas": finales, "primer_resultado": primero}


def credenciales(entorno: dict[str, str]) -> tuple[str, str]:
    correo = (entorno.get("CARGA_EMAIL") or "").strip() or input("Correo del usuario dueño del corpus: ").strip()
    clave = getpass.getpass("Contraseña (no se muestra): ")
    return correo, clave


def main(argumentos: list[str] | None = None) -> int:
    lector = argparse.ArgumentParser(description="Carga única e idempotente del corpus 2.0 en Supabase con el usuario que la ejecuta como dueño.")
    lector.add_argument("--forzar", action="store_true", help="Vuelve a subir las filas aunque el corpus ya esté completo.")
    opciones = lector.parse_args(argumentos)
    import sistema as si
    entorno = si.cargar_entorno()
    try:
        configuracion_supabase = al.ConfiguracionSupabase.desde_entorno(entorno)
        descargar_modelos.asegurar()
        corpus_id, configuracion, registros = preparar()
        correo, clave = credenciales(entorno)
        autenticacion = al.Autenticacion(configuracion_supabase)
        sesion = autenticacion.iniciar_sesion(correo, clave)
        del clave
        try:
            cliente = al.crear_cliente(configuracion_supabase, sesion.access_token)
            modelo = rc.ModeloEmbeddings(rc.CARPETA_MODELOS, rc.TokenizadorXLMR(rc.CARPETA_MODELOS / "embeddings/sentencepiece.bpe.model"))
            resultado = cargar(cliente, sesion.usuario_id, corpus_id, configuracion, registros, modelo.codificar, opciones.forzar)
        finally:
            autenticacion.cerrar_sesion(sesion.access_token, sesion.refresh_token)
    except (al.ErrorAlmacenamiento, ErrorCarga, OSError) as error:
        print(f"La carga no terminó: {error}", file=sys.stderr)
        return 1
    print(f"Corpus {resultado['modo']}. Filas verificadas: {resultado['filas']}.")
    print(f"La búsqueda remota y la exacta local coinciden en el primer resultado: {resultado['primer_resultado']}.")
    print("Agrega a app/.env:")
    print(f"CORPUS_ID={corpus_id}")
    print(f"CORPUS_PROPIETARIO_ID={sesion.usuario_id}")
    print("Para autorizar a un lector, ejecuta en el SQL Editor:")
    print("insert into public.lectores_corpus (propietario_id, corpus_id, lector_id) "
          f"select '{sesion.usuario_id}'::uuid, '{corpus_id}', id from auth.users where email = 'CORREO_DEL_LECTOR' on conflict do nothing;")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    sys.exit(main())
