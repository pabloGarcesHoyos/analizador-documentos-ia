import hashlib
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

URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7860").rstrip("/")
SALIDA = RAIZ / "evidencias" / "fase3"
CAPTURAS = SALIDA / "capturas"
ENTRADA = "Escribe tu pregunta o pega el texto de un documento"
SELECTOR_ENTRADA = f'textarea[placeholder="{ENTRADA}"]'
ESPERA_RESPUESTA = 150000
CREDENCIALES = dotenv_values(APP / ".env.pruebas")
CORREO_A, CLAVE_A = CREDENCIALES["PRUEBA_A_EMAIL"], CREDENCIALES["PRUEBA_A_PASSWORD"]
CORREO_B, CLAVE_B = CREDENCIALES["PRUEBA_B_EMAIL"], CREDENCIALES["PRUEBA_B_PASSWORD"]
CLAVES = [CLAVE_A, CLAVE_B]
PATRONES_SECRETOS = [re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), re.compile(r"gsk_[A-Za-z0-9]{10,}"),
                     re.compile(r"sb_(?:publishable|secret)_[A-Za-z0-9_-]{10,}")]
PALABRAS_INGLES = ["Submit", "Clear", "Loading", "Error", "Copy", "Retry", "Undo", "Share", "Built with", "Use via API", "Settings", "Download",
                   "Drop File", "Upload", "processing", "queue", "Click", "Like", "Dislike", "conversation", "message", "Remove", "Close"]
TERMINOS_INTERNOS = re.compile(r"\b(enrutador|flujo|ruta|herramienta|traza|RAG|MCP|LLM|Groq|prompt|json|OK_VALIDADO|OK_PIDE_ACLARACION|OK_REQUIERE_HUMANO|"
                               r"RESPONDIDA|ERROR_TECNICO|ERROR_VALIDACION|SIN_EVIDENCIA|PROPUESTA_INFORME|ACLARACION|RECHAZO)\b")
EMOJIS = re.compile("[" + chr(0x1F300) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF) + chr(0x2B00) + "-" + chr(0x2BFF) + "]")
TEXTOS_A_REVISAR: list[tuple[str, str]] = []
ATRIBUTOS_A_REVISAR: list[tuple[str, str]] = []


def limpiar(texto: str) -> str:
    texto = str(texto)
    for valor in (CLAVE_A, CLAVE_B, CORREO_A, CORREO_B):
        texto = texto.replace(valor, "<oculto>")
    for patron in PATRONES_SECRETOS:
        texto = patron.sub("<oculto>", texto)
    return texto


class Registro:
    def __init__(self):
        self.pasos: list[dict] = []
        self.extras: list[dict] = []
        self.consola: list[dict] = []
        self.http: list[dict] = []
        self.tiempos: list[dict] = []
        self.numero = 0

    def escuchar(self, pagina, nombre: str) -> None:
        pagina.on("console", lambda m: self.consola.append({"contexto": nombre, "tipo": m.type, "texto": limpiar(m.text)[:300]})
                  if m.type in ("error", "warning") else None)
        pagina.on("pageerror", lambda e: self.consola.append({"contexto": nombre, "tipo": "pageerror", "texto": limpiar(str(e))[:300]}))
        pagina.on("response", lambda r: self.http.append({"contexto": nombre, "estado": r.status, "metodo": r.request.method,
                                                          "url": limpiar(r.url.split("?")[0])}) if r.status >= 400 else None)

    def capturar(self, pagina, nombre: str, correo_visible: str | None = None) -> str:
        texto = pagina.locator("body").inner_text()
        for clave in CLAVES:
            if clave in texto:
                raise AssertionError("La captura mostraría una contraseña; no se guarda.")
        for patron in PATRONES_SECRETOS:
            if patron.search(texto):
                raise AssertionError("La captura mostraría un token o una clave; no se guarda.")
        for correo in (CORREO_A, CORREO_B):
            fuera = texto.replace(f"Sesión iniciada como {correo}", "")
            if correo in fuera:
                raise AssertionError("La captura mostraría un correo sin ocultar; no se guarda.")
        valores = pagina.evaluate("() => [...document.querySelectorAll('input[type=password]')].map(e => e.value)")
        if any(v in CLAVES for v in valores):
            raise AssertionError("Una caja de contraseña conserva la contraseña real; no se guarda la captura.")
        TEXTOS_A_REVISAR.append((nombre, texto))
        ATRIBUTOS_A_REVISAR.append((nombre, " | ".join(pagina.evaluate(
            "() => [...document.querySelectorAll('[aria-label],[title],[placeholder]')].filter(e => e.offsetParent !== null)"
            ".map(e => [e.getAttribute('aria-label'), e.getAttribute('title'), e.getAttribute('placeholder')].filter(Boolean).join(' '))"))))
        self.numero += 1
        ruta = CAPTURAS / f"{self.numero:02d}_{nombre}.png"
        mascaras = [pagina.get_by_text("Sesión iniciada como"), pagina.locator("input[type=email]")]
        pagina.screenshot(path=str(ruta), mask=mascaras, mask_color="#7a7a7a")
        return ruta.name

    def paso(self, numero: int, nombre: str, esperado: str, funcion) -> None:
        inicio = time.perf_counter()
        capturas: list[str] = []
        try:
            observado, aprobado = funcion(capturas)
        except Exception as error:
            observado, aprobado = f"Excepción: {limpiar(type(error).__name__ + ': ' + str(error))[:500]}", False
        self.pasos.append({"numero": numero, "nombre": nombre, "esperado": esperado, "observado": limpiar(observado), "capturas": capturas,
                           "estado": "aprobado" if aprobado else "fallido", "segundos": round(time.perf_counter() - inicio, 1)})
        print(f"paso {numero}: {'aprobado' if aprobado else 'fallido'}", flush=True)


R = Registro()


def iniciar_sesion(pagina, correo: str, clave: str) -> None:
    pagina.locator("input[type=email]").fill(correo)
    pagina.locator("input[type=password]").fill(clave)
    pagina.get_by_role("button", name="Iniciar sesión").click()
    pagina.get_by_text("Sesión iniciada como").wait_for(timeout=30000)


def entrada(pagina):
    return pagina.locator(SELECTOR_ENTRADA)


def texto_chat(pagina) -> str:
    return pagina.locator('[role="log"]').inner_text() if pagina.locator('[role="log"]').count() else ""


def ultima_respuesta(pagina) -> str:
    filas = pagina.locator(".message-row")
    textos = [(filas.nth(i).get_attribute("class") or "", filas.nth(i).inner_text()) for i in range(filas.count())]
    ultimo_usuario = max((i for i, (clase, _) in enumerate(textos) if "user-row" in clase), default=-1)
    return "\n".join(t for clase, t in textos[ultimo_usuario + 1:] if "bot-row" in clase)


def indicador(pagina) -> str:
    textos = pagina.evaluate("() => [...document.querySelectorAll('.prose')].filter(e => !e.closest('[role=log]') && e.offsetParent !== null)"
                             ".map(e => e.innerText.trim())")
    return next((t for t in textos if any(v in t for v in ap.ESTADOS.values()) or t.startswith("Conversación")), "")


def nueva(pagina) -> None:
    pagina.get_by_role("button", name="Nueva conversación").click()
    pagina.wait_for_timeout(500)


def enviar(pagina, texto: str, durante=None) -> int:
    filas_antes = pagina.locator(".message-row.bot-row").count()
    entrada(pagina).fill(texto)
    inicio = time.perf_counter()
    pagina.get_by_role("button", name="Enviar").click()
    if durante:
        pagina.wait_for_function(f"() => document.querySelector('{SELECTOR_ENTRADA}').disabled", timeout=5000)
        durante()
    pagina.wait_for_function(f"() => document.querySelectorAll('.message-row.bot-row').length > {filas_antes} "
                             f"&& !document.querySelector('{SELECTOR_ENTRADA}').disabled", timeout=ESPERA_RESPUESTA)
    pagina.wait_for_timeout(300)
    milisegundos = round((time.perf_counter() - inicio) * 1000)
    R.tiempos.append({"pregunta": texto, "ms": milisegundos})
    return milisegundos


def conversacion_actual(pagina) -> str | None:
    return pagina.evaluate("() => { const r = document.querySelector('input[type=radio]:checked'); return r ? r.value : null; }")


def ids_lista(pagina) -> list[str]:
    return pagina.evaluate("() => [...document.querySelectorAll('input[type=radio]')].map(r => r.value)")


def abrir(pagina, conversacion_id: str) -> None:
    pagina.locator(f'label:has(input[value="{conversacion_id}"])').click()
    pagina.wait_for_function(f"() => document.querySelector('input[value=\"{conversacion_id}\"]').checked", timeout=15000)
    pagina.wait_for_timeout(2500)


def boton_visible(pagina, nombre: str) -> bool:
    boton = pagina.get_by_role("button", name=nombre, exact=True)
    return boton.count() > 0 and boton.first.is_visible()


def secretos_en_navegador(contexto, pagina) -> list[str]:
    html = pagina.content()
    almacenes = pagina.evaluate("() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)])")
    cookies = json.dumps(contexto.cookies())
    hallazgos = []
    for nombre, texto in (("HTML", html), ("localStorage y sessionStorage", almacenes), ("cookies", cookies)):
        if any(c in texto for c in CLAVES):
            hallazgos.append(f"contraseña en {nombre}")
        for patron in PATRONES_SECRETOS:
            if patron.search(texto):
                hallazgos.append(f"token o clave en {nombre}")
        if "refresh_token" in texto or "access_token" in texto:
            hallazgos.append(f"nombre de token en {nombre}")
    return hallazgos


def pedir(metodo: str, ruta: str, cuerpo: dict | None = None) -> tuple[int, str]:
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    solicitud = urllib.request.Request(URL + ruta, data=datos, method=metodo, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(solicitud, timeout=20) as respuesta:
            return respuesta.status, respuesta.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read(500).decode("utf-8", "replace")


def main() -> None:
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for vieja in CAPTURAS.glob("*.png"):
        vieja.unlink()
    estado: dict = {}
    configuracion = al.ConfiguracionSupabase.desde_entorno(dotenv_values(APP / ".env"))
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto_a = navegador.new_context(locale="es-ES", viewport={"width": 1366, "height": 768}, accept_downloads=True)
        a = contexto_a.new_page()
        R.escuchar(a, "A")
        a.goto(URL)

        def paso1(c):
            a.locator("input[type=email]").fill(CORREO_A)
            a.locator("input[type=password]").fill("clave-incorrecta-de-prueba")
            a.get_by_role("button", name="Iniciar sesión").click()
            a.get_by_text("No se pudo iniciar sesión").wait_for(timeout=20000)
            vacia = a.locator("input[type=password]").input_value() == ""
            c.append(R.capturar(a, "login_contrasena_incorrecta"))
            aviso = a.get_by_text("No se pudo iniciar sesión").inner_text()
            return f"Aviso: \"{aviso}\". Caja de contraseña vacía: {'sí' if vacia else 'no'}.", vacia and "revisa el correo y la contraseña" in aviso
        R.paso(1, "Login de A con contraseña incorrecta", "Aviso claro y caja de contraseña vacía.", paso1)

        def paso2(c):
            inicio = time.perf_counter()
            iniciar_sesion(a, CORREO_A, CLAVE_A)
            ms = round((time.perf_counter() - inicio) * 1000)
            vacia = a.locator("input[type=password]").input_value() == ""
            c.append(R.capturar(a, "login_correcto"))
            visible = boton_visible(a, "Cerrar sesión") and a.locator(SELECTOR_ENTRADA).is_visible()
            return f"Entra a la vista de conversaciones en {ms} ms; caja de contraseña vacía: {'sí' if vacia else 'no'}.", visible and vacia
        R.paso(2, "Login correcto de A", "Entra a la aplicación y la contraseña no queda en la caja.", paso2)
        estado["ids_a_previos"] = set(ids_lista(a))

        def paso3(c):
            nueva(a)
            ms = enviar(a, "¿En qué estado está DOC-1001?")
            respuesta = ultima_respuesta(a)
            estado["estado"] = conversacion_actual(a)
            c.append(R.capturar(a, "estado_doc_1001"))
            ok = "[T1]" in respuesta and "Consultas: [T1]" in respuesta and "verificado_y_contabilizado" in respuesta and ap.ESTADOS["RESPONDIDA"] in indicador(a)
            return f"{ms} ms. Indicador: \"{indicador(a)}\". Respuesta: {respuesta[:400]}", ok
        R.paso(3, "Consulta de estado de DOC-1001", "Frase con [T1], bloque de consultas e indicador Respondida.", paso3)

        bloqueo: dict = {}

        def durante_mixta():
            bloqueo["entrada"] = entrada(a).is_disabled()
            bloqueo["botones"] = {n: a.get_by_role("button", name=n, exact=True).first.is_disabled() for n in ("Enviar", "Nueva conversación", "Cerrar sesión")}
            bloqueo["lista"] = a.evaluate("() => [...document.querySelectorAll('input[type=radio]')].every(r => r.disabled)")
            bloqueo["captura"] = R.capturar(a, "entrada_bloqueada_mientras_atiende")

        def paso4(c):
            nueva(a)
            ms = enviar(a, "¿Qué requisitos tiene una factura y en qué estado está DOC-1001?", durante_mixta)
            respuesta = ultima_respuesta(a)
            estado["mixta"] = conversacion_actual(a)
            c.append(R.capturar(a, "mixta_fuentes_y_consulta"))
            ok = all(t in respuesta for t in ("Fuentes: [F", "Documento:", "Sección:", "[T1]", "Consultas: [T1]"))
            return f"{ms} ms. Indicador: \"{indicador(a)}\". Respuesta: {respuesta[:700]}", ok
        R.paso(4, "Pregunta mixta de requisitos y estado", "Fuentes con documento, sección y pasaje, más [T1].", paso4)

        def paso5(c):
            nueva(a)
            ms = enviar(a, "¿Cómo va la revisión de mi documento?")
            respuesta = ultima_respuesta(a)
            c.append(R.capturar(a, "pide_codigo"))
            return f"{ms} ms. Indicador: \"{indicador(a)}\". Respuesta: {respuesta[:300]}", "DOC-XXXX o SOL-XXXX" in respuesta and ap.ESTADOS["ACLARACION"] in indicador(a)
        R.paso(5, "Seguimiento sin código", "Pide el código DOC-XXXX o SOL-XXXX.", paso5)

        def paso6(c):
            nueva(a)
            ms = enviar(a, "Elimina el documento DOC-1001")
            respuesta = ultima_respuesta(a)
            c.append(R.capturar(a, "rechazo_eliminar"))
            return f"{ms} ms. Indicador: \"{indicador(a)}\". Respuesta: {respuesta[:300]}", ap.ESTADOS["RECHAZO"] in indicador(a)
        R.paso(6, "Pedido de eliminar un documento", "Rechazo: el analizador solo consulta.", paso6)

        def paso7(c):
            nueva(a)
            ms = enviar(a, "Hola")
            respuesta = ultima_respuesta(a)
            c.append(R.capturar(a, "saludo"))
            internos = sorted(set(TERMINOS_INTERNOS.findall(respuesta)))
            return (f"{ms} ms. Indicador: \"{indicador(a)}\". Respuesta: {respuesta[:400]}. Términos internos: {internos or 'ninguno'}",
                    "Analizador de Documentos" in respuesta and not internos)
        R.paso(7, "Saludo", "Se presenta como el Analizador de Documentos, sin términos internos.", paso7)

        def paso8(c):
            if "captura" not in bloqueo:
                return "No se pudo observar el bloqueo durante la espera del paso 4.", False
            c.append(bloqueo["captura"])
            ok = bloqueo["entrada"] and all(bloqueo["botones"].values()) and bloqueo["lista"]
            return (f"Durante la espera del paso 4: entrada desactivada {bloqueo['entrada']}, botones desactivados {bloqueo['botones']}, "
                    f"lista de conversaciones desactivada {bloqueo['lista']}."), ok
        R.paso(8, "Bloqueo mientras atiende", "Entrada, botones y lista desactivados durante la espera.", paso8)

        def paso9(c):
            nueva(a)
            ms = enviar(a, "¿Qué datos debe traer una factura? Haz un informe")
            estado["informe_aprobar"] = conversacion_actual(a)
            contenido = a.get_by_label("Contenido completo del informe").input_value()
            destino = re.search(r"informe_[0-9a-f]{12}\.md", a.locator("body").inner_text())
            estado["contenido_aprobar"], estado["destino_aprobar"] = contenido, destino.group(0) if destino else ""
            c.append(R.capturar(a, "propuesta_de_informe"))
            primero = boton_visible(a, "Aprobar") and boton_visible(a, "Rechazar") and contenido.startswith("# Informe") and bool(destino)
            abrir(a, estado["estado"])
            oculto = not boton_visible(a, "Aprobar")
            c.append(R.capturar(a, "otra_conversacion_sin_panel"))
            abrir(a, estado["informe_aprobar"])
            otra_vez = boton_visible(a, "Aprobar") and a.get_by_role("button", name="Aprobar", exact=True).is_enabled()
            mismo = a.get_by_label("Contenido completo del informe").input_value() == contenido and estado["destino_aprobar"] in a.locator("body").inner_text()
            c.append(R.capturar(a, "propuesta_reaparece_al_volver"))
            return (f"{ms} ms. Indicador: \"{indicador(a)}\". Destino {estado['destino_aprobar']}; contenido de {len(contenido)} caracteres. "
                    f"Panel oculto en otra conversación: {oculto}. Al volver reaparecen Aprobar y Rechazar: {otra_vez}; mismo contenido y destino: {mismo}."), \
                primero and oculto and otra_vez and mismo
        R.paso(9, "Propuesta de informe y regreso a la conversación", "Contenido completo y destino; al volver reaparecen Aprobar y Rechazar.", paso9)

        def paso10(c):
            a.get_by_role("button", name="Aprobar", exact=True).dblclick()
            a.get_by_text("Informe aprobado, escrito y verificado").wait_for(timeout=60000)
            a.wait_for_timeout(1500)
            enlaces = a.locator("a[download]").filter(visible=True)
            cantidad = enlaces.count()
            with a.expect_download() as descarga:
                enlaces.first.click()
            ruta = Path(descarga.value.path())
            descargado = ruta.read_text(encoding="utf-8")
            igual = descargado == estado["contenido_aprobar"]
            c.append(R.capturar(a, "aprobado_un_solo_archivo"))
            autenticacion = al.Autenticacion(configuracion)
            sesion = autenticacion.iniciar_sesion(CORREO_A, CLAVE_A)
            decisiones = al.Almacenamiento(configuracion).decisiones_informe(sesion.access_token, estado["informe_aprobar"])
            autenticacion.cerrar_sesion(sesion.access_token, sesion.refresh_token)
            registradas = [(d["decision"], d["resultado"]) for d in decisiones.values()]
            return (f"Enlaces de descarga: {cantidad}. Contenido descargado igual al mostrado: {igual} "
                    f"(SHA-256 {hashlib.sha256(descargado.encode('utf-8')).hexdigest()[:12]}). Decisiones registradas en Supabase: {registradas}."), \
                cantidad == 1 and igual and registradas == [("aprobada", "ejecutada")]
        R.paso(10, "Doble clic en Aprobar", "Un solo archivo descargable, igual a lo mostrado; una sola decisión registrada.", paso10)

        def paso11(c):
            nueva(a)
            ms = enviar(a, "¿Qué datos debe traer una factura? Haz un informe")
            estado["informe_rechazar"] = conversacion_actual(a)
            visible = boton_visible(a, "Rechazar")
            a.get_by_role("button", name="Rechazar", exact=True).click()
            a.get_by_text("Rechazo registrado").wait_for(timeout=30000)
            c.append(R.capturar(a, "propuesta_rechazada"))
            return f"{ms} ms. Panel visible: {visible}. Aviso de rechazo registrado; enlaces de descarga visibles: {a.locator('a[download]').filter(visible=True).count()}.", \
                visible and a.locator("a[download]").filter(visible=True).count() == 0
        R.paso(11, "Otra propuesta y Rechazar", "Rechazo registrado y ningún archivo.", paso11)

        def paso12(c):
            abrir(a, estado["informe_aprobar"])
            aprobado = ultima_respuesta(a)
            sin_botones_1 = not boton_visible(a, "Aprobar")
            c.append(R.capturar(a, "decision_aprobada_al_reabrir"))
            abrir(a, estado["informe_rechazar"])
            rechazado = ultima_respuesta(a)
            sin_botones_2 = not boton_visible(a, "Aprobar")
            c.append(R.capturar(a, "decision_rechazada_al_reabrir"))
            ok = "aprobado y escrito" in aprobado and "rechazado; no se escribió ningún archivo" in rechazado and sin_botones_1 and sin_botones_2
            return f"Aprobada: nota presente {'aprobado y escrito' in aprobado}, sin botones {sin_botones_1}. Rechazada: nota presente {'rechazado' in rechazado}, sin botones {sin_botones_2}.", ok
        R.paso(12, "Reabrir las conversaciones decididas", "Se ve la decisión y no hay botones.", paso12)

        def paso13(c):
            abrir(a, estado["mixta"])
            antes_mixta = texto_chat(a)
            abrir(a, estado["estado"])
            antes_estado = texto_chat(a)
            c.append(R.capturar(a, "antes_de_recargar"))
            a.reload()
            a.locator("input[type=password]").wait_for(timeout=20000)
            pide = a.get_by_role("button", name="Iniciar sesión").is_visible() and not a.locator('[role="log"]').filter(visible=True).count()
            c.append(R.capturar(a, "recarga_pide_login"))
            iniciar_sesion(a, CORREO_A, CLAVE_A)
            abrir(a, estado["mixta"])
            despues_mixta = texto_chat(a)
            c.append(R.capturar(a, "mixta_tras_recargar"))
            abrir(a, estado["estado"])
            despues_estado = texto_chat(a)
            limitacion = "Limitación:" in antes_mixta
            ok = pide and antes_mixta == despues_mixta and antes_estado == despues_estado and "Fuentes: [F" in despues_mixta and "Consultas: [T1]" in despues_estado
            return (f"Pide login tras recargar: {pide}. Mixta idéntica: {antes_mixta == despues_mixta}. Estado idéntica: {antes_estado == despues_estado}. "
                    f"La respuesta mixta {'incluye' if limitacion else 'no incluye'} limitación."), ok
        R.paso(13, "Cambio entre conversaciones y recarga de la página", "Pide login y todo se ve idéntico: estado, limitación, fuentes y consultas.", paso13)
        estado["ids_a"] = set(ids_lista(a))
        estado["texto_a"] = "verificado_y_contabilizado"

        contexto_b = navegador.new_context(locale="es-ES", viewport={"width": 1366, "height": 768})
        b = contexto_b.new_page()
        R.escuchar(b, "B")

        def paso14(c):
            b.goto(URL)
            iniciar_sesion(b, CORREO_B, CLAVE_B)
            ids_b = set(ids_lista(b))
            comunes = ids_b & estado["ids_a"]
            c.append(R.capturar(b, "b_sin_conversaciones_de_a"))
            objetivo = estado["mixta"]
            b.goto(f"{URL}/?conversacion={objetivo}")
            iniciar_sesion(b, CORREO_B, CLAVE_B)
            por_url = objetivo not in ids_lista(b) and "verificado_y_contabilizado" not in texto_chat(b)
            c.append(R.capturar(b, "b_url_con_uuid_de_a"))
            info = b.evaluate("async (u) => { const r = await fetch(u + '/config'); return r.ok ? await r.json() : null; }", URL)
            intento = "sin configuración"
            negado = True
            if info:
                radio = next((x["id"] for x in info.get("components", []) if x.get("props", {}).get("label") == "Tus conversaciones"), None)
                indice = next((i for i, d in enumerate(info.get("dependencies", [])) if any(t[0] == radio for t in d.get("targets", []))), None)
                sesion_falsa = uuid.uuid4().hex[:11]
                codigo, cuerpo = pedir("POST", "/gradio_api/queue/join", {"data": [None, objetivo], "fn_index": indice, "session_hash": sesion_falsa,
                                                                         "event_data": None, "trigger_id": radio})
                intento = f"POST /gradio_api/queue/join al evento de selección con el UUID de A: HTTP {codigo}"
                if codigo == 200:
                    _, datos = pedir("GET", f"/gradio_api/queue/data?session_hash={sesion_falsa}")
                    negado = "verificado_y_contabilizado" not in datos and "Fuentes" not in datos
                    intento += f"; datos devueltos con contenido de A: {'no' if negado else 'sí'}"
            ok = not comunes and por_url and negado
            return (f"Conversaciones de A en la lista de B: {len(comunes)}. Por URL con el UUID de A: sin acceso {por_url}. "
                    f"La interfaz no tiene campo que acepte un UUID; la lista solo ofrece las de B. {intento}."), ok
        R.paso(14, "B en otro contexto al mismo tiempo que A", "B no ve nada de A y no puede cargar una conversación de A por la interfaz ni por la URL.", paso14)

        extras_secretos = {"A": secretos_en_navegador(contexto_a, a), "B": secretos_en_navegador(contexto_b, b)}

        def paso15(c):
            resultados = []
            for nombre, pagina in (("A", a), ("B", b)):
                pagina.get_by_role("button", name="Cerrar sesión").click()
                pagina.get_by_text("Sesión cerrada.").wait_for(timeout=20000)
                sin_datos = not pagina.locator('[role="log"]').filter(visible=True).count() and "verificado_y_contabilizado" not in pagina.locator("body").inner_text()
                c.append(R.capturar(pagina, f"cierre_de_sesion_{nombre.lower()}"))
                pagina.go_back()
                pagina.wait_for_timeout(3000)
                destino = pagina.url
                if not destino.startswith(URL):
                    pagina.go_forward()
                    pagina.wait_for_timeout(3000)
                atras = "Sesión iniciada como" not in pagina.locator("body").inner_text() and not pagina.locator('[role="log"]').filter(visible=True).count()
                atras = atras and pagina.locator("input[type=password]").is_visible()
                c.append(R.capturar(pagina, f"atras_tras_cerrar_{nombre.lower()}"))
                resultados.append((nombre, sin_datos, atras, "app" if destino.startswith(URL) else "página en blanco, luego Adelante"))
            return "; ".join(f"{n}: sin datos visibles tras cerrar {s}; Atrás llevó a {d} y muestra el inicio de sesión sin datos {t}" for n, s, t, d in resultados) + ".", \
                all(s and t for _, s, t, _ in resultados)
        R.paso(15, "Cerrar sesión en los dos", "No queda nada visible y Atrás no reutiliza la sesión.", paso15)

        for nombre, ancho, alto in (("escritorio_1366x768", 1366, 768), ("celular_390x844", 390, 844)):
            contexto = navegador.new_context(locale="es-ES", viewport={"width": ancho, "height": alto})
            pagina = contexto.new_page()
            R.escuchar(pagina, nombre)
            pagina.goto(URL)
            desborde_login = pagina.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth")
            capturas = [R.capturar(pagina, f"vista_{nombre}_login")]
            iniciar_sesion(pagina, CORREO_A, CLAVE_A)
            abrir(pagina, estado["mixta"])
            desborde_app = pagina.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth")
            capturas.append(R.capturar(pagina, f"vista_{nombre}_conversacion"))
            pagina.get_by_role("button", name="Cerrar sesión").click()
            R.extras.append({"revision": f"Vista {nombre}", "observado": f"Desborde horizontal en login: {desborde_login}; en conversación: {desborde_app}.",
                             "capturas": capturas, "estado": "aprobado" if not (desborde_login or desborde_app) else "fallido"})
            contexto.close()

        api_info = pedir("GET", "/gradio_api/info")
        api_llamada = pedir("POST", "/gradio_api/call/entrar", {"data": ["x", "y"]})
        navegador.close()

    ingles = sorted({p for _, t in TEXTOS_A_REVISAR for p in PALABRAS_INGLES if re.search(rf"\b{re.escape(p)}\b", t)})
    ingles_atributos = sorted({p for _, t in ATRIBUTOS_A_REVISAR for p in PALABRAS_INGLES if re.search(rf"\b{re.escape(p)}\b", t, re.IGNORECASE)})
    internos = sorted({m for _, t in TEXTOS_A_REVISAR for m in TERMINOS_INTERNOS.findall(t)})
    emojis = sorted({m for _, t in TEXTOS_A_REVISAR for m in EMOJIS.findall(t)})
    R.extras[:0] = [
        {"revision": "Texto visible en inglés", "observado": f"Palabras encontradas: {ingles or 'ninguna'}.", "capturas": [], "estado": "aprobado" if not ingles else "fallido"},
        {"revision": "Etiquetas de accesibilidad y textos emergentes en inglés", "observado": f"Palabras encontradas: {ingles_atributos or 'ninguna'}.", "capturas": [],
         "estado": "aprobado" if not ingles_atributos else "fallido"},
        {"revision": "Términos internos en el texto visible", "observado": f"Encontrados: {internos or 'ninguno'}.", "capturas": [], "estado": "aprobado" if not internos else "fallido"},
        {"revision": "Emojis en el texto visible", "observado": f"Encontrados: {len(emojis)}.", "capturas": [], "estado": "aprobado" if not emojis else "fallido"},
        {"revision": "Errores en la consola del navegador", "observado": f"{len([x for x in R.consola if x['tipo'] != 'warning'])} errores y "
         f"{len([x for x in R.consola if x['tipo'] == 'warning'])} advertencias: {R.consola[:8]}", "capturas": [],
         "estado": "aprobado" if not [x for x in R.consola if x["tipo"] != "warning"] else "fallido"},
        {"revision": "Respuestas HTTP 4xx o 5xx", "observado": f"{len(R.http)}: {R.http[:10]}", "capturas": [], "estado": "aprobado" if not R.http else "fallido"},
        {"revision": "Contraseñas o tokens en HTML, localStorage, sessionStorage y cookies", "observado": f"A: {extras_secretos['A'] or 'nada'}; B: {extras_secretos['B'] or 'nada'}.",
         "capturas": [], "estado": "aprobado" if not (extras_secretos["A"] or extras_secretos["B"]) else "fallido"},
        {"revision": "API de Gradio cerrada", "observado": f"GET /gradio_api/info: HTTP {api_info[0]}, {limpiar(api_info[1])[:120]}. "
         f"POST /gradio_api/call/entrar: HTTP {api_llamada[0]}, {limpiar(api_llamada[1])[:120]}.", "capturas": [],
         "estado": "aprobado" if api_info[1].strip() in ('{"named_endpoints":{},"unnamed_endpoints":{}}', "") and api_llamada[0] >= 400 else "fallido"},
        {"revision": "Tiempo de cada respuesta", "observado": "; ".join(f"\"{t['pregunta']}\": {t['ms']} ms" for t in R.tiempos) + ".", "capturas": [], "estado": "informativo"},
    ]
    escribir_informe()


def escribir_informe() -> None:
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=RAIZ).stdout.strip()
    fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    datos = {"fecha": fecha, "commit": commit, "url": URL, "navegador": "Chromium (Playwright 1.64.1)", "pasos": R.pasos, "revisiones": R.extras}
    (SALIDA / "prueba_interfaz.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    aprobados = sum(p["estado"] == "aprobado" for p in R.pasos)
    enlaces = lambda nombres: " ".join(f"[{n}](capturas/{n})" for n in nombres) or "sin captura"
    celda = lambda texto: str(texto).replace("|", "/").replace("\n", " ")
    lineas = ["# Fase 3: prueba de la interfaz en el navegador", "",
              f"Fecha: {fecha}. Commit: `{commit}`. URL: {URL}. Navegador: Chromium con Playwright 1.64.1, idioma es-ES.", "",
              f"Resultado: {aprobados} de {len(R.pasos)} pasos aprobados.", "",
              "Las credenciales se leen de `app/.env.pruebas` dentro del script y no se imprimen. En las capturas, el correo de la sesión y la caja de correo "
              "se cubren con un recuadro gris; antes de guardar cada captura el script comprueba que no se vea ninguna contraseña, token ni clave.", "",
              "Comando: `python app/tests/e2e/prueba_interfaz.py http://127.0.0.1:7860` con la aplicación corriendo.", "",
              "## Pasos", "", "| Paso | Esperado | Observado | Capturas | Tiempo (s) | Estado |", "|---|---|---|---|---|---|"]
    for p in R.pasos:
        lineas.append(f"| {p['numero']}. {p['nombre']} | {celda(p['esperado'])} | {celda(p['observado'])} | {enlaces(p['capturas'])} | {p['segundos']} | {p['estado']} |")
    lineas += ["", "## Revisiones adicionales", "", "| Revisión | Observado | Capturas | Estado |", "|---|---|---|---|"]
    for r in R.extras:
        lineas.append(f"| {r['revision']} | {celda(r['observado'])} | {enlaces(r['capturas'])} | {r['estado']} |")
    (SALIDA / "prueba_interfaz.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"{aprobados} de {len(R.pasos)} pasos aprobados", flush=True)


if __name__ == "__main__":
    main()
