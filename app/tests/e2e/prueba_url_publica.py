import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[3]
APP = RAIZ / "app"
sys.path.insert(0, str(APP))

import almacenamiento as al
import app as ap

SALIDA = RAIZ / "evidencias" / "fase4"
CAPTURAS = SALIDA / "capturas"
ESTADO_REINICIO = SALIDA / "conversaciones_antes_del_reinicio.json"
CREDENCIALES = dotenv_values(APP / ".env.pruebas")
CLAVES = [CREDENCIALES[k] for k in ("PRUEBA_A_PASSWORD", "PRUEBA_B_PASSWORD", "PRUEBA_DEMO_PASSWORD")]
CORREOS = [CREDENCIALES[k] for k in ("PRUEBA_A_EMAIL", "PRUEBA_B_EMAIL", "PRUEBA_DEMO_EMAIL")]
SECRETOS = [re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), re.compile(r"gsk_[A-Za-z0-9]{10,}"), re.compile(r"sb_(?:publishable|secret)_[A-Za-z0-9_-]{10,}")]
ENTRADA = 'textarea[placeholder="Escribe tu pregunta o pega el texto de un documento"]'
PREGUNTA_SIN_EVIDENCIA = "¿Cuál es el plazo para pagar una factura después de contabilizarla?"
ESPERADO_SIN_EVIDENCIA = ("El corpus 2.0 no trata plazos de pago. Esperado: estado sin evidencia, o parcial con una limitación que diga que los documentos "
                          "no indican el plazo de pago; ninguna frase afirma un plazo de pago; si menciona los 90 días, es como regla de radicación y con su cita.")
PREGUNTA_ESTADO = "¿En qué estado está DOC-1001?"
PREGUNTA_MIXTA = "¿Qué requisitos tiene una factura y en qué estado está DOC-1001?"
PREGUNTA_FALLA = "¿Qué datos debe traer una factura para contabilizarla?"


def limpiar(texto: str) -> str:
    for valor in CLAVES + CORREOS:
        texto = texto.replace(valor, "<oculto>")
    for patron in SECRETOS:
        texto = patron.sub("<oculto>", texto)
    return texto


def capturar(pagina, nombre: str) -> str:
    texto = pagina.locator("body").inner_text()
    if any(c in texto for c in CLAVES) or any(p.search(texto) for p in SECRETOS):
        raise AssertionError("La captura mostraría una contraseña o un token; no se guarda.")
    if any(c in texto.replace(f"Sesión iniciada como {c}", "") for c in CORREOS):
        raise AssertionError("La captura mostraría un correo sin cubrir; no se guarda.")
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    ruta = CAPTURAS / f"{nombre}.png"
    pagina.screenshot(path=str(ruta), mask=[pagina.get_by_text("Sesión iniciada como"), pagina.locator("input[type=email]")], mask_color="#7a7a7a")
    return ruta.name


def entrar(pagina, url: str, prefijo: str) -> None:
    pagina.goto(url, timeout=180000)
    pagina.locator("input[type=email]").fill(CREDENCIALES[f"PRUEBA_{prefijo}_EMAIL"])
    pagina.locator("input[type=password]").fill(CREDENCIALES[f"PRUEBA_{prefijo}_PASSWORD"])
    pagina.get_by_role("button", name="Iniciar sesión").click()
    pagina.get_by_text("Sesión iniciada como").wait_for(timeout=90000)
    pagina.wait_for_timeout(1000)


def chat(pagina) -> str:
    return pagina.locator('[role="log"]').inner_text() if pagina.locator('[role="log"]').count() else ""


def indicador(pagina) -> str:
    textos = pagina.evaluate("() => [...document.querySelectorAll('.prose')].filter(e => !e.closest('[role=log]') && e.offsetParent !== null)"
                             ".map(e => e.innerText.trim())")
    conocidos = list(ap.ESTADOS.values()) + list(ap.ROTULOS_POR_RUTA.values()) + [ap.PROCESANDO, ap.ESPERANDO_CUPO]
    return next((t for t in textos if any(t.startswith(v) for v in conocidos) or t.startswith("Conversación")), "")


def preguntar(pagina, texto: str) -> int:
    pagina.get_by_role("button", name="Nueva conversación").click()
    pagina.wait_for_timeout(800)
    pagina.locator(ENTRADA).fill(texto)
    inicio = time.perf_counter()
    pagina.get_by_role("button", name="Enviar").click()
    pagina.wait_for_function(f"() => document.querySelectorAll('.message-row.bot-row').length > 0 && !document.querySelector('{ENTRADA}').disabled",
                             timeout=180000)
    pagina.wait_for_timeout(600)
    return round((time.perf_counter() - inicio) * 1000)


def conversacion_actual(pagina) -> str | None:
    return pagina.evaluate("() => { const r = document.querySelector('input[type=radio]:checked'); return r ? r.value : null; }")


def panel_abierto(pagina) -> bool:
    return pagina.evaluate("() => { const b = document.querySelector('#panel-conversaciones .label-wrap'); return !!b && b.classList.contains('open'); }")


def abrir(pagina, conversacion_id: str, contiene: str) -> None:
    if not panel_abierto(pagina):
        pagina.locator("#panel-conversaciones .label-wrap").click()
    antes = chat(pagina)
    pagina.locator(f'label:has(input[value="{conversacion_id}"])').click()
    pagina.wait_for_function(
        """([id, antes, contiene]) => { const r = document.querySelector(`input[value="${id}"]`); const c = document.querySelector('[role=log]');
            const t = c ? c.innerText : ''; return r && r.checked && t !== antes && t.includes(contiene); }""",
        arg=[conversacion_id, antes, contiene], timeout=60000)
    pagina.wait_for_timeout(800)


def todas(pagina) -> list[str]:
    while pagina.get_by_role("button", name="Ver más", exact=True).count() and pagina.get_by_role("button", name="Ver más", exact=True).first.is_visible():
        antes = pagina.locator("input[type=radio]").count()
        pagina.get_by_role("button", name="Ver más", exact=True).click()
        pagina.wait_for_function(f"() => document.querySelectorAll('input[type=radio]').length > {antes}", timeout=60000)
    return pagina.evaluate("() => [...document.querySelectorAll('input[type=radio]')].map(r => r.value)")


def ids_de(prefijo: str) -> set[str]:
    configuracion = al.ConfiguracionSupabase.desde_entorno(dotenv_values(APP / ".env"))
    autenticacion = al.Autenticacion(configuracion)
    sesion = autenticacion.iniciar_sesion(CREDENCIALES[f"PRUEBA_{prefijo}_EMAIL"], CREDENCIALES[f"PRUEBA_{prefijo}_PASSWORD"])
    try:
        return {c["id"] for c in al.Almacenamiento(configuracion).listar_conversaciones(sesion.access_token, al.MAX_CONVERSACIONES)}
    finally:
        autenticacion.cerrar_sesion(sesion.access_token, sesion.refresh_token)


def pedir(url: str, metodo: str, ruta: str, cuerpo: dict) -> tuple[int, str]:
    solicitud = urllib.request.Request(url + ruta, data=json.dumps(cuerpo).encode(), method=metodo, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(solicitud, timeout=60) as respuesta:
            return respuesta.status, respuesta.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read(500).decode("utf-8", "replace")


def registro(numero: str, nombre: str, entrada: str, esperado: str, observado: str, capturas: list[str], aprobado: bool) -> dict:
    return {"numero": numero, "nombre": nombre, "entrada": entrada, "esperado": esperado, "observado": limpiar(observado), "capturas": capturas,
            "estado": "aprobado" if aprobado else "fallido"}


def etapa_antes(url: str) -> list[dict]:
    resultados = []
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto = navegador.new_context(locale="es-ES", viewport={"width": 1366, "height": 768})
        pagina = contexto.new_page()
        entrar(pagina, url, "DEMO")
        ms = preguntar(pagina, PREGUNTA_SIN_EVIDENCIA)
        respuesta, rotulo = chat(pagina), indicador(pagina)
        afirma_plazo = any(re.search(r"pag", o, re.IGNORECASE) and re.search(r"\d+\s*d[ií]as", o) for o in re.split(r"(?<=[.!?])\s+", respuesta))
        aprobado = (rotulo.startswith(ap.ESTADOS["SIN_EVIDENCIA"]) or (rotulo.startswith("Respondida en parte") and "Limitación:" in respuesta)) and not afirma_plazo
        resultados.append(registro("1", "Pregunta del dominio sin evidencia en el corpus", PREGUNTA_SIN_EVIDENCIA, ESPERADO_SIN_EVIDENCIA,
                                   f"{ms} ms. Indicador: \"{rotulo}\". Afirma un plazo de pago: {afirma_plazo}. Respuesta: {respuesta[:700]}",
                                   [capturar(pagina, "01_sin_evidencia")], aprobado))
        preguntar(pagina, PREGUNTA_ESTADO)
        estado_id = conversacion_actual(pagina)
        preguntar(pagina, PREGUNTA_MIXTA)
        mixta_id = conversacion_actual(pagina)
        abrir(pagina, estado_id, PREGUNTA_ESTADO)
        texto_estado = chat(pagina)
        captura_estado = capturar(pagina, "02a_estado_antes_del_reinicio")
        abrir(pagina, mixta_id, PREGUNTA_MIXTA)
        texto_mixta = chat(pagina)
        captura_mixta = capturar(pagina, "02a_mixta_antes_del_reinicio")
        ESTADO_REINICIO.parent.mkdir(parents=True, exist_ok=True)
        ESTADO_REINICIO.write_text(json.dumps({"estado": {"id": estado_id, "chat": texto_estado}, "mixta": {"id": mixta_id, "chat": texto_mixta}},
                                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        resultados.append(registro("2a", "Conversaciones creadas antes del reinicio", f"{PREGUNTA_ESTADO} / {PREGUNTA_MIXTA}",
                                   "Dos conversaciones guardadas: estado con [T1] y mixta con [F#] y [T1].",
                                   f"Estado con [T1]: {'[T1]' in texto_estado}. Mixta con fuentes y consulta: {'Fuentes:' in texto_mixta and 'Consultas: [T1]' in texto_mixta}.",
                                   [captura_estado, captura_mixta], "[T1]" in texto_estado and "Fuentes:" in texto_mixta))
        pagina.get_by_role("button", name="Cerrar sesión").click()

        ids_a, ids_demo = ids_de("A"), ids_de("DEMO")
        contexto_a = navegador.new_context(locale="es-ES", viewport={"width": 1366, "height": 768})
        contexto_b = navegador.new_context(locale="es-ES", viewport={"width": 1366, "height": 768})
        a, b = contexto_a.new_page(), contexto_b.new_page()
        entrar(a, url, "A")
        entrar(b, url, "B")
        capturas = [capturar(a, "03_a_en_su_contexto")]
        lista_b = set(todas(b))
        comunes = lista_b & (ids_a | ids_demo)
        capturas.append(capturar(b, "03_b_sin_conversaciones_de_a"))
        objetivo = sorted(ids_a)[0]
        b.goto(f"{url}/?conversacion={objetivo}", timeout=180000)
        entrar(b, url, "B")
        por_url = objetivo not in todas(b) and not chat(b).strip()
        capturas.append(capturar(b, "03_b_url_con_uuid_de_a"))
        configuracion = json.loads(urllib.request.urlopen(url + "/config", timeout=60).read())
        radio = next((x["id"] for x in configuracion.get("components", []) if x.get("props", {}).get("label") == "Conversaciones recientes"), None)
        indice = next((i for i, d in enumerate(configuracion.get("dependencies", [])) if any(t[0] == radio for t in d.get("targets", []))), None)
        codigo, cuerpo = pedir(url, "POST", "/gradio_api/queue/join", {"data": [None, objetivo], "fn_index": indice, "session_hash": uuid.uuid4().hex[:11],
                                                                      "event_data": None, "trigger_id": radio})
        sin_datos = 400 <= codigo < 500 and not any(m in cuerpo for m in ("role", "Respondida", "Fuentes", "contenido"))
        resultados.append(registro("3", "Aislamiento en la URL pública", "A y B con sesión al mismo tiempo; B intenta abrir una conversación de A por la lista, "
                                   "por la URL y por una llamada directa a la cola",
                                   "B no ve ninguna conversación de A ni del demo; la URL con el UUID no la abre; la llamada directa termina en 4xx sin datos.",
                                   f"Conversaciones ajenas en la lista completa de B: {len(comunes)} de {len(ids_a | ids_demo)}. Por URL: sin acceso {por_url}. "
                                   f"Llamada directa: HTTP {codigo}, sin datos {sin_datos}.", capturas, not comunes and por_url and sin_datos))
        for pagina_cierre in (a, b):
            pagina_cierre.get_by_role("button", name="Cerrar sesión").click()
        navegador.close()
    return resultados


def etapa_despues(url: str) -> list[dict]:
    guardado = json.loads(ESTADO_REINICIO.read_text(encoding="utf-8"))
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_context(locale="es-ES", viewport={"width": 1366, "height": 768}).new_page()
        entrar(pagina, url, "DEMO")
        abrir(pagina, guardado["estado"]["id"], PREGUNTA_ESTADO)
        igual_estado = chat(pagina) == guardado["estado"]["chat"]
        captura_estado = capturar(pagina, "02c_estado_despues_del_reinicio")
        abrir(pagina, guardado["mixta"]["id"], PREGUNTA_MIXTA)
        igual_mixta = chat(pagina) == guardado["mixta"]["chat"]
        captura_mixta = capturar(pagina, "02c_mixta_despues_del_reinicio")
        pagina.get_by_role("button", name="Cerrar sesión").click()
        navegador.close()
    return [registro("2c", "Conversaciones tras reiniciar el servicio en Render", "Volver a entrar con demo y abrir las dos conversaciones",
                     "Las dos conversaciones se ven idénticas a antes del reinicio.", f"Estado idéntica: {igual_estado}. Mixta idéntica: {igual_mixta}.",
                     [captura_estado, captura_mixta], igual_estado and igual_mixta)]


def etapa_falla(url: str) -> list[dict]:
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_context(locale="es-ES", viewport={"width": 1366, "height": 768}).new_page()
        entrar(pagina, url, "DEMO")
        ms = preguntar(pagina, PREGUNTA_FALLA)
        respuesta, rotulo = chat(pagina), indicador(pagina)
        captura = capturar(pagina, "04_error_tecnico_con_clave_invalida")
        pagina.get_by_role("button", name="Cerrar sesión").click()
        navegador.close()
    aprobado = rotulo.startswith(ap.ESTADOS["ERROR_TECNICO"]) and ap.ESTADOS["SIN_EVIDENCIA"] not in respuesta and "No significa que falte información" in respuesta
    return [registro("4", "Falla técnica controlada (local, GROQ_API_KEY inválida solo en el entorno del proceso)", PREGUNTA_FALLA,
                     "Se muestra como error técnico, con la aclaración de que no significa falta de información; distinto de sin evidencia.",
                     f"{ms} ms. Indicador: \"{rotulo}\". Respuesta: {respuesta[:400]}", [captura], aprobado)]


def informe(url: str) -> None:
    commit = subprocess.run(["gh", "api", "repos/pabloGarcesHoyos/analizador-documentos-ia/deployments", "--jq", ".[0].sha"], capture_output=True, text=True,
                            cwd=RAIZ).stdout.strip()[:7]
    filas = []
    for nombre in ("antes", "despues", "falla"):
        archivo = SALIDA / f"resultados_{nombre}.json"
        if archivo.exists():
            filas += json.loads(archivo.read_text(encoding="utf-8"))["pasos"]
    orden = {"1": 0, "2a": 1, "2c": 2, "3": 3, "4": 4}
    filas.sort(key=lambda f: orden.get(f["numero"], 9))
    fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    celda = lambda t: str(t).replace("|", "/").replace("\n", " ")
    lineas = ["# Fase 4: pruebas en la URL publicada", "",
              f"Fecha: {fecha}. URL: {url}. Commit desplegado en Render: `{commit}`. Navegador: Chromium con Playwright 1.64.1, idioma es-ES.", "",
              f"Resultado: {sum(f['estado'] == 'aprobado' for f in filas)} de {len(filas)} aprobadas.", "",
              "Las credenciales se leen de `app/.env.pruebas` dentro del script y no se imprimen. En las capturas, el correo de la sesión se cubre con un "
              "recuadro gris; antes de guardar cada captura el script comprueba que no se vea ninguna contraseña, token ni clave. El paso 4 se corre en local "
              "porque necesita una clave inválida inyectada solo en el entorno del proceso.", "",
              "Comandos: `python app/tests/e2e/prueba_url_publica.py antes <url>`, reinicio manual del servicio en Render, "
              "`python app/tests/e2e/prueba_url_publica.py despues <url>`, `python app/tests/e2e/prueba_url_publica.py falla http://127.0.0.1:7861` y "
              "`python app/tests/e2e/prueba_url_publica.py informe <url>`.", "",
              "| Prueba | Entrada | Esperado (escrito antes de correr) | Observado | Capturas | Estado |", "|---|---|---|---|---|---|"]
    for f in filas:
        enlaces = " ".join(f"[{c}](capturas/{c})" for c in f["capturas"])
        lineas.append(f"| {f['numero']}. {f['nombre']} | {celda(f['entrada'])} | {celda(f['esperado'])} | {celda(f['observado'])} | {enlaces} | {f['estado']} |")
    (SALIDA / "pruebas_url_publica.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main() -> None:
    etapa, url = sys.argv[1], sys.argv[2].rstrip("/")
    if etapa == "informe":
        informe(url)
        return
    pasos = {"antes": etapa_antes, "despues": etapa_despues, "falla": etapa_falla}[etapa](url)
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / f"resultados_{etapa}.json").write_text(json.dumps({"etapa": etapa, "url": url, "fecha": datetime.now(timezone.utc).isoformat(), "pasos": pasos},
                                                                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for paso in pasos:
        print(f"{paso['numero']}: {paso['estado']}", flush=True)


if __name__ == "__main__":
    main()
