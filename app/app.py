import asyncio
import hashlib
import inspect
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import gradio as gr
from starlette.middleware import Middleware
from starlette.responses import JSONResponse

import almacenamiento as al
import sistema as si

MARGEN_REFRESCO = 120
LARGO_TITULO = 60
CONCURRENCIA_ATENCION = 1
CONCURRENCIA_GENERAL = 2
MAX_COLA = 16
LIMPIEZA_ARCHIVOS = (1800, 1800)
TITULO_APP = "Analizador de Documentos"
TAMANO_PAGINA = 20
PROCESANDO = "Procesando tu consulta…"
ESPERANDO_CUPO = "Esperando cupo del proveedor del modelo…"
SESION_NO_VALIDA = "Sesión no válida."
RUTAS_BLOQUEADAS = re.compile(r"^/gradio_api/(run|api|call|info|openapi\.json|mcp|upload|upload_progress|deep_link|run-history|runs|monitoring)(/|$)"
                              r"|^/(monitoring|runs)(/|$)")
ESTILOS = ('#chat-analizador button[aria-label="Clear"], #chat-analizador button[aria-label="Borrar"], '
           '#chat-analizador button[aria-label="Limpiar chat"] {display: none !important;}')
CABECERA = """<script>
(() => {
  const etiquetas = {"chatbot conversation": "Conversación con el analizador", "Clear": "Borrar", "Copy": "Copiar", "Copy message": "Copiar mensaje",
    "Copy conversation": "Copiar conversación", "Download": "Descargar", "Loading": "Cargando", "Share": "Compartir", "Remove": "Quitar",
    "Undo": "Deshacer", "Retry": "Reintentar", "Edit": "Editar", "Close": "Cerrar", "Scroll down": "Bajar al final"};
  const prefijos = [["user's message: ", "Mensaje del usuario: "], ["bot's message: ", "Respuesta del analizador: "]];
  let plegado = false;
  let intentos = 0;
  let programado = false;
  const plegar = () => {
    programado = false;
    const panel = document.getElementById("panel-conversaciones");
    const boton = panel && panel.offsetParent !== null ? panel.querySelector(".label-wrap") : null;
    if (!boton) return;
    if (!boton.classList.contains("open")) {
      plegado = true;
      return;
    }
    if (intentos < 10) {
      intentos += 1;
      boton.click();
      programar();
    }
  };
  const programar = () => {
    if (!programado) {
      programado = true;
      setTimeout(plegar, 250);
    }
  };
  const traducir = (valor) => {
    if (valor in etiquetas) return etiquetas[valor];
    for (const [ingles, espanol] of prefijos) if (valor.startsWith(ingles)) return espanol + valor.slice(ingles.length);
    return valor;
  };
  const ajustar = () => {
    if (document.documentElement.lang !== "es") document.documentElement.lang = "es";
    document.querySelectorAll('[data-testid="status-tracker"]').forEach((elemento) => elemento.remove());
    for (const atributo of ["aria-label", "title"]) {
      document.querySelectorAll("[" + atributo + "]").forEach((elemento) => {
        const actual = elemento.getAttribute(atributo);
        const nuevo = traducir(actual);
        if (nuevo !== actual) elemento.setAttribute(atributo, nuevo);
      });
    }
    const panel = document.getElementById("panel-conversaciones");
    if (panel && panel.offsetParent !== null) {
      if (window.innerWidth >= 768) plegado = true;
      if (!plegado) programar();
    } else {
      plegado = false;
      intentos = 0;
    }
  };
  new MutationObserver(ajustar).observe(document.documentElement, {subtree: true, childList: true, attributes: true, attributeFilter: ["aria-label", "title"]});
})();
</script>"""

ESTADOS = {
    "RESPONDIDA": "Respondida con evidencia de los documentos.",
    "PARCIAL": "Respondida en parte: revisa la limitación indicada.",
    "PROPUESTA_INFORME": "Respondida. Hay una propuesta de informe que espera tu aprobación.",
    "ACLARACION": "Se necesita una aclaración para continuar.",
    "SIN_EVIDENCIA": "Sin evidencia: los documentos disponibles no responden esta pregunta.",
    "RECHAZO": "Solicitud rechazada: el analizador solo consulta información.",
    "ERROR_TECNICO": "Error técnico: no se pudo completar la solicitud. No significa que falte información; intenta de nuevo.",
    "ERROR_VALIDACION": "Error de validación: la respuesta generada no superó el control de citas y no se muestra.",
    "LIMITE_TIEMPO": "Tiempo agotado: la solicitud tardó demasiado; intenta de nuevo.",
    "SIN_ACCESO_CORPUS": "Sin acceso: tu usuario no está autorizado para consultar los documentos de políticas.",
    "ACCESO_DENEGADO": "La conversación no existe o no pertenece a tu usuario.",
    "ERROR_ENTRADA": "La pregunta no es válida: revisa su longitud.",
    "SESION_INVALIDA": "La sesión venció; vuelve a iniciar sesión.",
}
OPERACIONES = {"consultar_estado_solicitud": "Consulta de estado en el registro", "clasificar_documento": "Clasificación del documento"}
DECISIONES_CLASIFICACION = {"OK_VALIDADO": "documento validado", "OK_PIDE_ACLARACION": "faltan datos o requiere aclaración",
                            "OK_REQUIERE_HUMANO": "requiere revisión humana", "ERROR_FORMATO": "la clasificación no cumplió el formato"}
CAMPOS_PRIMERO = ("estado", "detalle")
DECISIONES_INFORME = {("aprobada", "ejecutada"): "aprobado y escrito", ("aprobada", "fallida"): "aprobado, pero la escritura falló y no se reintenta",
                      ("aprobada", None): "aprobado, sin escritura confirmada", ("rechazada", None): "rechazado; no se escribió ningún archivo"}
AVISO_INICIO = "Escribe una pregunta para empezar una conversación nueva."
AVISO_VENCIDA = "La sesión venció y no se pudo renovar. Vuelve a iniciar sesión."


def texto_estado(estado: str | None) -> str:
    return ESTADOS.get(estado or "", "Estado desconocido.")


def titulo_automatico(texto: str) -> str:
    limpio = " ".join((texto or "").split())
    if len(limpio) <= LARGO_TITULO:
        return limpio or "Conversación"
    corte = limpio[:LARGO_TITULO].rsplit(" ", 1)[0] or limpio[:LARGO_TITULO]
    return corte + "..."


def _valor(valor: Any) -> str:
    if isinstance(valor, list):
        return ", ".join(str(v) for v in valor) or "ninguno"
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    return str(valor)


def bloque_fuentes(fuentes: list[dict]) -> str:
    partes = []
    for fuente in fuentes:
        partes.append(f"**[{fuente.get('etiqueta')}]** Documento: {fuente.get('source')}. Sección: {fuente.get('section')}. "
                      f"Versión: {fuente.get('version')}.\n\n> " + str(fuente.get("texto", "")).replace("\n", "\n> "))
    return "\n\n".join(partes)


def orden_campo(clave: str) -> tuple[int, str]:
    return (CAMPOS_PRIMERO.index(clave) if clave in CAMPOS_PRIMERO else len(CAMPOS_PRIMERO), clave)


def bloque_herramientas(herramientas: list[dict]) -> str:
    partes = []
    for herramienta in herramientas:
        resultado = herramienta.get("resultado") or {}
        nombre = OPERACIONES.get(herramienta.get("operacion"), "Consulta")
        encabezado = f"**[{herramienta.get('etiqueta')}]** {nombre}" + ("" if herramienta.get("citada") else " (no citada en la respuesta)")
        if herramienta.get("operacion") == "consultar_estado_solicitud":
            lineas = [f"Código consultado: {resultado.get('codigo_solicitud')}", f"Registro: {resultado.get('fuente')}",
                      f"Encontrado: {_valor(bool(resultado.get('encontrado')))}"]
            registro = resultado.get("registro") or {}
            lineas += [f"{clave.replace('_', ' ').capitalize()}: {_valor(registro[clave])}" for clave in sorted(registro, key=orden_campo)]
        else:
            clasificacion = resultado.get("clasificacion") or {}
            lineas = [f"Resultado: {DECISIONES_CLASIFICACION.get(resultado.get('decision'), resultado.get('decision'))}"]
            if clasificacion:
                lineas += [f"Tipo de documento: {clasificacion.get('tipo_documento')}", f"Nivel de riesgo: {clasificacion.get('nivel_riesgo')}",
                           f"Resumen: {clasificacion.get('resumen_contenido')}", f"Campos faltantes: {_valor(clasificacion.get('campos_faltantes') or [])}"]
        partes.append(encabezado + "\n\n" + "\n".join(f"- {linea}" for linea in lineas))
    return "\n\n".join(partes)


def mensajes_asistente(estado: str, contenido: str, fuentes: list[dict], herramientas: list[dict], limitacion: str = "", detalle: str = "") -> list[dict]:
    texto = f"**{texto_estado(estado)}**\n\n{contenido}"
    if limitacion:
        texto += f"\n\nLimitación: {limitacion}"
    if detalle:
        texto += f"\n\nDetalle: {detalle}"
    mensajes = [{"role": "assistant", "content": texto}]
    if fuentes:
        mensajes.append({"role": "assistant", "content": bloque_fuentes(fuentes),
                         "metadata": {"title": "Fuentes: " + " ".join(f"[{f.get('etiqueta')}]" for f in fuentes)}})
    if herramientas:
        mensajes.append({"role": "assistant", "content": bloque_herramientas(herramientas),
                         "metadata": {"title": "Consultas: " + " ".join(f"[{h.get('etiqueta')}]" for h in herramientas)}})
    return mensajes


def mensajes_de_fila(fila: dict) -> list[dict]:
    if fila.get("rol") == "usuario":
        return [{"role": "user", "content": fila.get("contenido", "")}]
    detalle = (fila.get("detalle_error") or "") if fila.get("estado") == "ERROR_TECNICO" else ""
    return mensajes_asistente(fila.get("estado"), fila.get("contenido", ""), fila.get("fuentes") or [], fila.get("herramientas") or [],
                              fila.get("limitacion") or "", detalle)


def fila_de_resultado(resultado: si.ResultadoAtencion) -> dict:
    return {"rol": "asistente", "contenido": resultado.respuesta, "estado": resultado.estado, "fuentes": resultado.fuentes,
            "herramientas": resultado.herramientas, "limitacion": resultado.limitacion,
            "detalle_error": resultado.detalle_error}


def mensaje_decision(destino: str, accion: dict) -> dict:
    texto = DECISIONES_INFORME.get((accion.get("decision"), accion.get("resultado")), "con una decisión registrada")
    return {"role": "assistant", "content": f"Informe `{destino}`: {texto}.", "metadata": {"title": "Decisión sobre el informe"}}


def panel_propuesta(conversacion_id: str, mensaje_id: int, propuesta: dict) -> dict:
    contenido = propuesta.get("contenido") or ""
    if hashlib.sha256(contenido.encode("utf-8")).hexdigest() != propuesta.get("huella_contenido"):
        return {}
    return {"propuesta": {"conversacion_id": conversacion_id, "mensaje_id": mensaje_id, "destino": propuesta["destino"], "contenido": contenido,
                          "huella": propuesta["huella_contenido"]},
            "informe": gr.update(visible=True), "archivo": gr.update(visible=False, value=None), "aviso_informe": "",
            "informe_destino": f"Destino: `{propuesta['destino']}`, en la carpeta de informes de tu usuario. Revisa el contenido completo antes de decidir.",
            "informe_contenido": contenido, "aprobar": gr.update(interactive=True), "rechazar": gr.update(interactive=True)}


def _oculto() -> dict:
    return gr.update(visible=False)


def _informe_oculto() -> dict:
    return {"propuesta": None, "informe": _oculto(), "archivo": gr.update(visible=False, value=None), "aviso_informe": ""}


def _controles(activos: bool) -> dict:
    return {nombre: gr.update(interactive=activos) for nombre in ("entrada", "enviar", "nueva", "salir", "lista")}


def es_actualizacion(valor: Any) -> bool:
    return isinstance(valor, dict) and valor.get("__type__") == "update"


def unir(*partes: dict) -> dict:
    salida: dict = {}
    for parte in partes:
        for clave, valor in parte.items():
            salida[clave] = {**salida[clave], **valor} if es_actualizacion(valor) and es_actualizacion(salida.get(clave)) else valor
    return salida


def vista_inicio(mensaje: str = "") -> dict:
    return {"sesion": None, "conversacion": None, "vista_login": gr.update(visible=True), "vista_app": _oculto(), "aviso_login": mensaje,
            "clave": "", "usuario": "", "chat": [], "indicador": "", "lista": gr.update(choices=[], value=None), "limite": TAMANO_PAGINA,
            "ver_mas": gr.update(visible=False), **_informe_oculto()}


def sesion_valida(sesion: Any) -> bool:
    return isinstance(sesion, dict) and isinstance(sesion.get("access_token"), str) and bool(sesion["access_token"]) \
        and isinstance(sesion.get("refresh_token"), str) and isinstance(sesion.get("expira_en"), (int, float))


def exigir_sesion(sesion: Any, *resto: Any) -> Any:
    if not sesion_valida(sesion):
        raise gr.Error(SESION_NO_VALIDA, print_exception=False)
    validos = [gr.validate(True, "") for _ in range(1 + len(resto))]
    return validos[0] if len(validos) == 1 else validos


class BloqueoApi:
    def __init__(self, aplicacion):
        self.aplicacion = aplicacion

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and RUTAS_BLOQUEADAS.match(scope.get("path", "")):
            await JSONResponse({"detail": "No disponible."}, status_code=404)(scope, receive, send)
            return
        await self.aplicacion(scope, receive, send)


def opciones_lista(conversaciones: list[dict]) -> list[tuple[str, str]]:
    return [(c.get("titulo") or "Conversación", c["id"]) for c in conversaciones]


class Interfaz:
    def __init__(self, autenticacion: al.Autenticacion, almacen: al.Almacenamiento, sistema: si.Sistema, reloj=time.time):
        self.autenticacion = autenticacion
        self.almacen = almacen
        self.sistema = sistema
        self.reloj = reloj
        self._decisiones_en_curso: set[tuple[str, int]] = set()

    def _vigente(self, sesion: dict | None) -> dict:
        if not sesion or not sesion.get("access_token"):
            raise al.SesionInvalida("No hay una sesión iniciada.")
        if sesion["expira_en"] - self.reloj() > MARGEN_REFRESCO:
            return sesion
        nueva = self.autenticacion.refrescar(sesion["refresh_token"]).como_estado()
        nueva["correo"] = nueva["correo"] or sesion.get("correo", "")
        return nueva

    def _lista(self, token: str, conversacion: str | None, limite: int) -> dict:
        limite = max(TAMANO_PAGINA, min(int(limite or TAMANO_PAGINA), al.MAX_CONVERSACIONES))
        conversaciones = self.almacen.listar_conversaciones(token, min(limite + 1, al.MAX_CONVERSACIONES))
        hay_mas = len(conversaciones) > limite
        visibles = conversaciones[:limite]
        if conversacion and conversacion not in [c["id"] for c in visibles]:
            conversacion = None
        return {"lista": gr.update(choices=opciones_lista(visibles), value=conversacion), "ver_mas": gr.update(visible=hay_mas), "limite": limite}

    def entrar(self, correo: str, clave: str) -> dict:
        try:
            sesion = self.autenticacion.iniciar_sesion(correo, clave).como_estado()
            lista = self._lista(sesion["access_token"], None, TAMANO_PAGINA)
        except (al.CredencialesInvalidas, al.ServicioNoDisponible, al.SesionInvalida) as error:
            return {"sesion": None, "clave": "", "aviso_login": str(error)}
        except al.ErrorAlmacenamiento:
            return {"sesion": None, "clave": "", "aviso_login": "No se pudo cargar tu historial por un error técnico; intenta de nuevo."}
        return unir(_controles(True), {"sesion": sesion, "conversacion": None, "clave": "", "aviso_login": "", "vista_login": _oculto(),
                                        "vista_app": gr.update(visible=True), "usuario": f"Sesión iniciada como {sesion['correo']}", "chat": [],
                                        "indicador": AVISO_INICIO, **_informe_oculto()}, lista)

    def ver_mas(self, sesion: dict | None, limite: int, conversacion: str | None) -> dict:
        try:
            sesion = self._vigente(sesion)
            return {"sesion": sesion, **self._lista(sesion["access_token"], conversacion, (limite or TAMANO_PAGINA) + TAMANO_PAGINA)}
        except al.SesionInvalida:
            return vista_inicio(AVISO_VENCIDA)
        except al.ErrorAlmacenamiento:
            return {"sesion": sesion, "indicador": "No se pudo cargar la lista de conversaciones por un error técnico; intenta de nuevo."}

    def salir(self, sesion: dict | None) -> dict:
        if sesion and sesion.get("access_token"):
            self.autenticacion.cerrar_sesion(sesion["access_token"], sesion.get("refresh_token", ""))
        return vista_inicio("Sesión cerrada.")

    def nueva(self, sesion: dict | None = None) -> dict:
        return {"conversacion": None, "chat": [], "lista": gr.update(value=None), "indicador": "Conversación nueva: se guardará al enviar la primera pregunta.",
                **_informe_oculto()}

    def seleccionar(self, sesion: dict | None, conversacion_id: str | None) -> dict:
        if not conversacion_id:
            return {}
        try:
            sesion = self._vigente(sesion)
            filas, decisiones = self.almacen.cargar_conversacion(sesion["access_token"], conversacion_id)
        except al.SesionInvalida:
            return vista_inicio(AVISO_VENCIDA)
        except (al.AccesoDenegado, al.DatosInvalidos):
            return {"sesion": sesion, "conversacion": None, "chat": [], "lista": gr.update(value=None), "indicador": ESTADOS["ACCESO_DENEGADO"],
                    **_informe_oculto()}
        except al.ErrorAlmacenamiento:
            return {"sesion": sesion, "indicador": "No se pudo cargar el historial por un error técnico; intenta de nuevo."}
        chat, pendiente = [], None
        for fila in filas:
            chat += mensajes_de_fila(fila)
            propuesta = fila.get("propuesta_informe") if fila.get("rol") == "asistente" else None
            if propuesta and fila["id"] in decisiones:
                chat.append(mensaje_decision(propuesta["destino"], decisiones[fila["id"]]))
            elif propuesta:
                pendiente = (fila["id"], propuesta)
        ultimo = next((f for f in reversed(filas) if f.get("rol") == "asistente"), None)
        panel = panel_propuesta(conversacion_id, pendiente[0], pendiente[1]) if pendiente else {}
        salida = {"sesion": sesion, "conversacion": conversacion_id, "chat": chat, "indicador": indicador_recarga(ultimo, bool(panel), decisiones),
                  **_informe_oculto()}
        salida.update(panel)
        return salida

    def bloquear(self, sesion: dict | None, texto: str, chat: list[dict]) -> dict:
        if not (texto or "").strip():
            return {}
        return {**_controles(False), "chat": list(chat or []) + [{"role": "user", "content": texto}], "indicador": PROCESANDO}

    async def responder_en_vivo(self, sesion: dict | None, conversacion: str | None, texto: str, chat: list[dict], limite: int = TAMANO_PAGINA):
        avisos: asyncio.Queue = asyncio.Queue()
        tarea = asyncio.ensure_future(self.responder(sesion, conversacion, texto, chat, limite, al_esperar=avisos.put_nowait))
        while not tarea.done():
            siguiente = asyncio.ensure_future(avisos.get())
            listos, _ = await asyncio.wait({tarea, siguiente}, return_when=asyncio.FIRST_COMPLETED)
            if siguiente in listos:
                yield {"indicador": ESPERANDO_CUPO}
            else:
                siguiente.cancel()
        try:
            final = tarea.result()
        except Exception:
            final = {"indicador": ESTADOS["ERROR_TECNICO"]}
        yield unir(_controles(True), final)

    async def responder(self, sesion: dict | None, conversacion: str | None, texto: str, chat: list[dict], limite: int = TAMANO_PAGINA,
                        al_esperar: Any = None) -> dict:
        texto = texto or ""
        if not texto.strip():
            return {"indicador": "Escribe una pregunta antes de enviar."}
        try:
            sesion = await asyncio.to_thread(self._vigente, sesion)
            token = sesion["access_token"]
            if conversacion is None:
                conversacion = (await asyncio.to_thread(self.almacen.crear_conversacion, token, titulo_automatico(texto)))["id"]
        except al.SesionInvalida:
            return vista_inicio(AVISO_VENCIDA)
        except al.ErrorAlmacenamiento:
            return {"sesion": sesion, "chat": list(chat or [])[:-1], "indicador": "No se pudo crear la conversación por un error técnico; intenta de nuevo."}
        resultado = await self.sistema.atender(texto, conversacion, token, al_esperar=al_esperar)
        if resultado.estado == "SESION_INVALIDA":
            return vista_inicio(AVISO_VENCIDA)
        chat = list(chat or [])
        if not chat or chat[-1].get("role") != "user":
            chat.append({"role": "user", "content": texto})
        chat += mensajes_de_fila(fila_de_resultado(resultado))
        indicador = texto_estado(resultado.estado)
        if not resultado.persistido:
            indicador += " Este turno no se pudo guardar en el historial."
        salida = {"sesion": sesion, "conversacion": conversacion, "chat": chat, "indicador": indicador,
                  "entrada": gr.update(value="" if resultado.estado != "ERROR_ENTRADA" else texto), **_informe_oculto()}
        try:
            salida.update(await asyncio.to_thread(self._lista, token, conversacion, limite))
        except al.ErrorAlmacenamiento:
            pass
        if resultado.propuesta_informe and resultado.persistido and resultado.mensaje_id:
            salida.update(panel_propuesta(conversacion, resultado.mensaje_id, resultado.propuesta_informe))
        return salida

    def bloquear_informe(self, sesion: dict | None = None) -> dict:
        return {"aprobar": gr.update(interactive=False), "rechazar": gr.update(interactive=False)}

    async def aprobar(self, sesion: dict | None, propuesta: dict | None, chat: list[dict] | None = None) -> dict:
        return await self._decidir(sesion, propuesta, "aprobada", chat)

    async def rechazar(self, sesion: dict | None, propuesta: dict | None, chat: list[dict] | None = None) -> dict:
        return await self._decidir(sesion, propuesta, "rechazada", chat)

    async def _decidir(self, sesion: dict | None, propuesta: dict | None, decision: str, chat: list[dict] | None) -> dict:
        if not propuesta:
            return {"aviso_informe": "Esta propuesta ya fue atendida; no se repite la acción."}
        clave = (propuesta["conversacion_id"], propuesta["mensaje_id"])
        if clave in self._decisiones_en_curso:
            return {"aviso_informe": "La decisión sobre este informe ya está en curso; no se repite."}
        self._decisiones_en_curso.add(clave)
        try:
            salida = await self._ejecutar_decision(sesion, propuesta, decision)
            if salida.get("propuesta", propuesta) is None and salida.get("sesion", sesion):
                await self._anotar_decision(salida, salida.get("sesion") or sesion, propuesta, chat)
            return salida
        finally:
            self._decisiones_en_curso.discard(clave)

    async def _anotar_decision(self, salida: dict, sesion: dict, propuesta: dict, chat: list[dict] | None) -> None:
        if chat is None:
            return
        try:
            decisiones = await asyncio.to_thread(self.almacen.decisiones_informe, sesion["access_token"], propuesta["conversacion_id"])
        except al.ErrorAlmacenamiento:
            return
        if propuesta["mensaje_id"] in decisiones:
            nota = mensaje_decision(propuesta["destino"], decisiones[propuesta["mensaje_id"]])
            salida["chat"] = _quitar_nota(list(chat), nota) + [nota]

    async def _ejecutar_decision(self, sesion: dict | None, propuesta: dict, decision: str) -> dict:
        try:
            sesion = await asyncio.to_thread(self._vigente, sesion)
            token = sesion["access_token"]
            accion = await asyncio.to_thread(self.almacen.registrar_decision_informe, token, propuesta["conversacion_id"], propuesta["mensaje_id"],
                                             decision, propuesta["destino"], propuesta["huella"])
        except al.SesionInvalida:
            return vista_inicio(AVISO_VENCIDA)
        except al.AccionYaRegistrada:
            return {"sesion": sesion, "propuesta": None, "aviso_informe": "La decisión sobre este informe ya estaba registrada; no se repite."}
        except al.ErrorAlmacenamiento:
            return {"sesion": sesion, "aviso_informe": "No se pudo registrar la decisión por un error técnico. No se escribió nada; puedes intentarlo de nuevo.",
                    "aprobar": gr.update(interactive=True), "rechazar": gr.update(interactive=True)}
        if decision == "rechazada":
            return {"sesion": sesion, "propuesta": None, "aviso_informe": "Rechazo registrado. No se escribió ningún archivo."}
        try:
            escrito = await self.sistema.escribir_informe_aprobado(token, accion["id"], propuesta["contenido"])
        except si.InformeNoAutorizado as error:
            return {"sesion": sesion, "propuesta": None, "aviso_informe": f"No se escribió el informe: {error}"}
        except si.ErrorTecnico:
            return {"sesion": sesion, "propuesta": None,
                    "aviso_informe": "No se pudo escribir el informe por un error técnico. Quedó registrado como fallido y no se reintenta."}
        except al.ErrorAlmacenamiento:
            return {"sesion": sesion, "propuesta": None, "aviso_informe": "No se pudo confirmar el resultado del informe por un error técnico."}
        try:
            datos = Path(escrito["ruta"]).read_bytes()
        except OSError:
            datos = b""
        if hashlib.sha256(datos).hexdigest() != propuesta["huella"]:
            return {"sesion": sesion, "propuesta": None, "aviso_informe": "El archivo escrito no coincide con el aprobado; no se ofrece para descargar."}
        descarga = Path(tempfile.mkdtemp(prefix="informe_")) / propuesta["destino"]
        descarga.write_bytes(datos)
        return {"sesion": sesion, "propuesta": None, "archivo": gr.update(visible=True, value=str(descarga)),
                "aviso_informe": "Informe aprobado, escrito y verificado. Descárgalo ahora: el servidor no guarda los informes de forma permanente."}


def indicador_recarga(ultimo: dict | None, pendiente: bool, decisiones: dict) -> str:
    if pendiente:
        return "Conversación cargada. Hay una propuesta de informe que espera tu aprobación."
    if not ultimo:
        return "Conversación cargada, todavía sin mensajes."
    if ultimo.get("estado") == "PROPUESTA_INFORME" and ultimo.get("id") in decisiones:
        return "Conversación cargada. La propuesta de informe ya tiene una decisión registrada."
    return f"Conversación cargada. Última respuesta: {texto_estado(ultimo.get('estado'))}"


def _quitar_nota(chat: list[dict], nota: dict) -> list[dict]:
    return chat[:-1] if chat and chat[-1] == nota else chat


def _mapear(resultado: dict, componentes: dict) -> dict:
    return {componentes[nombre]: valor for nombre, valor in resultado.items()}


def _envolver(funcion, componentes: dict):
    if inspect.isasyncgenfunction(funcion):
        async def envuelta(*argumentos):
            async for parcial in funcion(*argumentos):
                yield _mapear(parcial, componentes)
    elif asyncio.iscoroutinefunction(funcion):
        async def envuelta(*argumentos):
            return _mapear(await funcion(*argumentos), componentes)
    else:
        def envuelta(*argumentos):
            return _mapear(funcion(*argumentos), componentes)
    return envuelta


def construir(interfaz: Interfaz) -> gr.Blocks:
    with gr.Blocks(title=TITULO_APP, delete_cache=LIMPIEZA_ARCHIVOS) as demo:
        c: dict[str, Any] = {"sesion": gr.State(None), "conversacion": gr.State(None), "propuesta": gr.State(None), "limite": gr.State(TAMANO_PAGINA)}
        with gr.Column(visible=True) as vista_login:
            gr.Markdown(f"# {TITULO_APP}\n\nInicia sesión con tu cuenta para consultar políticas, estados de documentos y solicitudes.")
            c["correo"] = gr.Textbox(label="Correo", type="email", max_lines=1)
            c["clave"] = gr.Textbox(label="Contraseña", type="password", max_lines=1)
            c["entrar"] = gr.Button("Iniciar sesión", variant="primary")
            c["aviso_login"] = gr.Markdown("")
        with gr.Row(visible=False) as vista_app:
            with gr.Column(scale=1, min_width=220):
                c["usuario"] = gr.Markdown("")
                c["nueva"] = gr.Button("Nueva conversación")
                with gr.Accordion("Tus conversaciones", open=True, elem_id="panel-conversaciones"):
                    c["lista"] = gr.Radio(label="Conversaciones recientes", choices=[], value=None)
                    c["ver_mas"] = gr.Button("Ver más", visible=False, size="sm")
                c["salir"] = gr.Button("Cerrar sesión", variant="secondary")
            with gr.Column(scale=3):
                c["indicador"] = gr.Markdown("")
                c["chat"] = gr.Chatbot(label="Conversación", height=520, sanitize_html=True, buttons=[], feedback_options=None, elem_id="chat-analizador")
                with gr.Row():
                    c["entrada"] = gr.Textbox(label="Pregunta", placeholder="Escribe tu pregunta o pega el texto de un documento", lines=2, scale=4)
                    c["enviar"] = gr.Button("Enviar", variant="primary", scale=1)
                with gr.Group(visible=False) as informe:
                    gr.Markdown("### Propuesta de informe\n\nEscribir el informe es una acción que necesita tu aprobación.")
                    c["informe_destino"] = gr.Markdown("")
                    c["informe_contenido"] = gr.Textbox(label="Contenido completo del informe", lines=14, interactive=False)
                    with gr.Row():
                        c["aprobar"] = gr.Button("Aprobar", variant="primary")
                        c["rechazar"] = gr.Button("Rechazar", variant="stop")
                    c["aviso_informe"] = gr.Markdown("")
                    c["archivo"] = gr.File(label="Informe para descargar", visible=False, interactive=False)
        c.update(vista_login=vista_login, vista_app=vista_app, informe=informe)
        todo = [c[n] for n in ("sesion", "conversacion", "propuesta", "limite", "vista_login", "vista_app", "aviso_login", "clave", "usuario", "chat",
                               "indicador", "lista", "ver_mas", "informe", "archivo", "aviso_informe")]
        controles = [c[n] for n in ("entrada", "enviar", "nueva", "salir", "lista")]
        informe_salidas = [c[n] for n in ("informe_destino", "informe_contenido", "aprobar", "rechazar")]
        comun = {"api_visibility": "private", "show_progress": "hidden"}
        protegido = {**comun, "validator": exigir_sesion}
        for disparador in (c["entrar"].click, c["clave"].submit):
            disparador(_envolver(interfaz.entrar, c), [c["correo"], c["clave"]], todo + controles, concurrency_limit=CONCURRENCIA_GENERAL, **comun)
        c["salir"].click(_envolver(interfaz.salir, c), [c["sesion"]], todo, **protegido)
        c["nueva"].click(_envolver(interfaz.nueva, c), [c["sesion"]], [c["conversacion"], c["chat"], c["lista"], c["indicador"], c["propuesta"],
                                                                    c["informe"], c["archivo"], c["aviso_informe"]], **protegido)
        c["ver_mas"].click(_envolver(interfaz.ver_mas, c), [c["sesion"], c["limite"], c["conversacion"]], todo, concurrency_limit=CONCURRENCIA_GENERAL,
                           **protegido)
        c["lista"].input(_envolver(interfaz.seleccionar, c), [c["sesion"], c["lista"]], todo + informe_salidas, concurrency_limit=CONCURRENCIA_GENERAL,
                         **protegido)
        for disparador in (c["enviar"].click, c["entrada"].submit):
            (disparador(_envolver(interfaz.bloquear, c), [c["sesion"], c["entrada"], c["chat"]], controles + [c["chat"], c["indicador"]], **protegido)
             .then(_envolver(interfaz.responder_en_vivo, c), [c["sesion"], c["conversacion"], c["entrada"], c["chat"], c["limite"]],
                   todo + controles + informe_salidas, concurrency_limit=CONCURRENCIA_ATENCION, concurrency_id="atencion", **protegido))
        for boton, manejador in ((c["aprobar"], interfaz.aprobar), (c["rechazar"], interfaz.rechazar)):
            (boton.click(_envolver(interfaz.bloquear_informe, c), [c["sesion"]], [c["aprobar"], c["rechazar"]], **protegido)
             .then(_envolver(manejador, c), [c["sesion"], c["propuesta"], c["chat"]], todo + [c["aprobar"], c["rechazar"]],
                   concurrency_limit=CONCURRENCIA_ATENCION, concurrency_id="atencion", **protegido))
    return demo


def opciones_lanzamiento(servidor: str, puerto: int) -> dict:
    return {"server_name": servidor, "server_port": puerto, "share": False, "show_error": False, "footer_links": [], "head": CABECERA, "css": ESTILOS,
            "app_kwargs": {"middleware": [Middleware(BloqueoApi)]}}


def preparar(demo: gr.Blocks) -> gr.Blocks:
    return demo.queue(default_concurrency_limit=CONCURRENCIA_GENERAL, max_size=MAX_COLA, api_open=False)


def cargar_configuracion(entorno: dict[str, str]) -> tuple[si.ConfiguracionSistema, str, int]:
    configuracion = si.ConfiguracionSistema.desde_entorno(entorno)
    servidor = (entorno.get("GRADIO_SERVER_NAME") or "127.0.0.1").strip()
    puerto = (entorno.get("PORT") or "7860").strip()
    if not puerto.isdigit() or not 1 <= int(puerto) <= 65535:
        raise al.ConfiguracionInvalida("PORT debe ser un número de puerto entre 1 y 65535.")
    return configuracion, servidor, int(puerto)


def main() -> None:
    try:
        configuracion, servidor, puerto = cargar_configuracion(si.cargar_entorno())
    except al.ConfiguracionInvalida as error:
        sys.exit(f"La aplicación no arranca: {error}")
    import descargar_modelos
    descargar_modelos.asegurar()
    sistema = si.Sistema(configuracion)
    interfaz = Interfaz(al.Autenticacion(configuracion.supabase), sistema.almacen, sistema)
    demo = preparar(construir(interfaz))
    demo.launch(**opciones_lanzamiento(servidor, puerto))


if __name__ == "__main__":
    main()
