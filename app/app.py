import asyncio
import hashlib
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import gradio as gr

import almacenamiento as al
import sistema as si

MARGEN_REFRESCO = 120
LARGO_TITULO = 60
CONCURRENCIA_ATENCION = 1
CONCURRENCIA_GENERAL = 2
MAX_COLA = 16
LIMPIEZA_ARCHIVOS = (1800, 1800)
TITULO_APP = "Analizador de Documentos"

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


def bloque_herramientas(herramientas: list[dict]) -> str:
    partes = []
    for herramienta in herramientas:
        resultado = herramienta.get("resultado") or {}
        nombre = OPERACIONES.get(herramienta.get("operacion"), "Consulta")
        encabezado = f"**[{herramienta.get('etiqueta')}]** {nombre}" + ("" if herramienta.get("citada") else " (no citada en la respuesta)")
        if herramienta.get("operacion") == "consultar_estado_solicitud":
            lineas = [f"Código consultado: {resultado.get('codigo_solicitud')}", f"Registro: {resultado.get('fuente')}",
                      f"Encontrado: {_valor(bool(resultado.get('encontrado')))}"]
            lineas += [f"{clave.replace('_', ' ').capitalize()}: {_valor(valor)}" for clave, valor in (resultado.get("registro") or {}).items()]
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
    return mensajes_asistente(fila.get("estado"), fila.get("contenido", ""), fila.get("fuentes") or [], fila.get("herramientas") or [])


def _oculto() -> dict:
    return gr.update(visible=False)


def _informe_oculto() -> dict:
    return {"propuesta": None, "informe": _oculto(), "archivo": gr.update(visible=False, value=None), "aviso_informe": ""}


def _controles(activos: bool) -> dict:
    return {nombre: gr.update(interactive=activos) for nombre in ("entrada", "enviar", "nueva", "salir", "lista")}


def vista_inicio(mensaje: str = "") -> dict:
    return {"sesion": None, "conversacion": None, "vista_login": gr.update(visible=True), "vista_app": _oculto(), "aviso_login": mensaje,
            "clave": "", "usuario": "", "chat": [], "indicador": "", "lista": gr.update(choices=[], value=None), **_informe_oculto()}


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

    def entrar(self, correo: str, clave: str) -> dict:
        try:
            sesion = self.autenticacion.iniciar_sesion(correo, clave).como_estado()
            conversaciones = self.almacen.listar_conversaciones(sesion["access_token"])
        except (al.CredencialesInvalidas, al.ServicioNoDisponible, al.SesionInvalida) as error:
            return {"sesion": None, "clave": "", "aviso_login": str(error)}
        except al.ErrorAlmacenamiento:
            return {"sesion": None, "clave": "", "aviso_login": "No se pudo cargar tu historial por un error técnico; intenta de nuevo."}
        return {"sesion": sesion, "conversacion": None, "clave": "", "aviso_login": "", "vista_login": _oculto(), "vista_app": gr.update(visible=True),
                "usuario": f"Sesión iniciada como {sesion['correo']}", "lista": gr.update(choices=opciones_lista(conversaciones), value=None),
                "chat": [], "indicador": AVISO_INICIO, **_informe_oculto()}

    def salir(self, sesion: dict | None) -> dict:
        if sesion and sesion.get("access_token"):
            self.autenticacion.cerrar_sesion(sesion["access_token"], sesion.get("refresh_token", ""))
        return vista_inicio("Sesión cerrada.")

    def nueva(self) -> dict:
        return {"conversacion": None, "chat": [], "lista": gr.update(value=None), "indicador": "Conversación nueva: se guardará al enviar la primera pregunta.",
                **_informe_oculto()}

    def seleccionar(self, sesion: dict | None, conversacion_id: str | None) -> dict:
        if not conversacion_id:
            return {}
        try:
            sesion = self._vigente(sesion)
            filas = self.almacen.cargar_mensajes(sesion["access_token"], conversacion_id)
        except al.SesionInvalida:
            return vista_inicio(AVISO_VENCIDA)
        except (al.AccesoDenegado, al.DatosInvalidos):
            return {"conversacion": None, "chat": [], "lista": gr.update(value=None), "indicador": ESTADOS["ACCESO_DENEGADO"], **_informe_oculto()}
        except al.ErrorAlmacenamiento:
            return {"indicador": "No se pudo cargar el historial por un error técnico; intenta de nuevo."}
        chat = [mensaje for fila in filas for mensaje in mensajes_de_fila(fila)]
        ultimo = next((f.get("estado") for f in reversed(filas) if f.get("rol") == "asistente"), None)
        indicador = f"Conversación cargada. Última respuesta: {texto_estado(ultimo)}" if ultimo else "Conversación cargada, todavía sin mensajes."
        return {"sesion": sesion, "conversacion": conversacion_id, "chat": chat, "indicador": indicador, **_informe_oculto()}

    def bloquear(self, texto: str, chat: list[dict]) -> dict:
        if not (texto or "").strip():
            return {}
        return {**_controles(False), "chat": list(chat or []) + [{"role": "user", "content": texto}], "indicador": "Atendiendo tu pregunta..."}

    def desbloquear(self) -> dict:
        return _controles(True)

    async def responder(self, sesion: dict | None, conversacion: str | None, texto: str, chat: list[dict]) -> dict:
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
            return {"chat": list(chat or [])[:-1], "indicador": "No se pudo crear la conversación por un error técnico; intenta de nuevo."}
        resultado = await self.sistema.atender(texto, conversacion, token)
        if resultado.estado == "SESION_INVALIDA":
            return vista_inicio(AVISO_VENCIDA)
        chat = list(chat or [])
        if not chat or chat[-1].get("role") != "user":
            chat.append({"role": "user", "content": texto})
        chat += mensajes_asistente(resultado.estado, resultado.respuesta, resultado.fuentes, resultado.herramientas, resultado.limitacion,
                                   resultado.detalle_error if resultado.estado == "ERROR_TECNICO" else "")
        indicador = texto_estado(resultado.estado)
        if not resultado.persistido:
            indicador += " Este turno no se pudo guardar en el historial."
        salida = {"sesion": sesion, "conversacion": conversacion, "chat": chat, "indicador": indicador,
                  "entrada": "" if resultado.estado != "ERROR_ENTRADA" else texto, **_informe_oculto()}
        try:
            conversaciones = await asyncio.to_thread(self.almacen.listar_conversaciones, token)
            salida["lista"] = gr.update(choices=opciones_lista(conversaciones), value=conversacion)
        except al.ErrorAlmacenamiento:
            pass
        propuesta = resultado.propuesta_informe
        if propuesta and resultado.persistido and resultado.mensaje_id:
            salida.update({"propuesta": {"conversacion_id": conversacion, "mensaje_id": resultado.mensaje_id, "destino": propuesta["destino"],
                                         "contenido": propuesta["contenido"], "huella": propuesta["huella_contenido"]},
                           "informe": gr.update(visible=True),
                           "informe_destino": f"Destino: `{propuesta['destino']}`, en la carpeta de informes de tu usuario. Revisa el contenido completo antes de decidir.",
                           "informe_contenido": propuesta["contenido"], "aprobar": gr.update(interactive=True), "rechazar": gr.update(interactive=True)})
        return salida

    def bloquear_informe(self) -> dict:
        return {"aprobar": gr.update(interactive=False), "rechazar": gr.update(interactive=False)}

    async def aprobar(self, sesion: dict | None, propuesta: dict | None) -> dict:
        return await self._decidir(sesion, propuesta, "aprobada")

    async def rechazar(self, sesion: dict | None, propuesta: dict | None) -> dict:
        return await self._decidir(sesion, propuesta, "rechazada")

    async def _decidir(self, sesion: dict | None, propuesta: dict | None, decision: str) -> dict:
        if not propuesta:
            return {"aviso_informe": "Esta propuesta ya fue atendida; no se repite la acción."}
        clave = (propuesta["conversacion_id"], propuesta["mensaje_id"])
        if clave in self._decisiones_en_curso:
            return {"aviso_informe": "La decisión sobre este informe ya está en curso; no se repite."}
        self._decisiones_en_curso.add(clave)
        try:
            return await self._ejecutar_decision(sesion, propuesta, decision)
        finally:
            self._decisiones_en_curso.discard(clave)

    async def _ejecutar_decision(self, sesion: dict | None, propuesta: dict, decision: str) -> dict:
        try:
            sesion = await asyncio.to_thread(self._vigente, sesion)
            token = sesion["access_token"]
            accion = await asyncio.to_thread(self.almacen.registrar_decision_informe, token, propuesta["conversacion_id"], propuesta["mensaje_id"],
                                             decision, propuesta["destino"], propuesta["huella"])
        except al.SesionInvalida:
            return vista_inicio(AVISO_VENCIDA)
        except al.AccionYaRegistrada:
            return {"propuesta": None, "aviso_informe": "La decisión sobre este informe ya estaba registrada; no se repite."}
        except al.ErrorAlmacenamiento:
            return {"aviso_informe": "No se pudo registrar la decisión por un error técnico. No se escribió nada; puedes intentarlo de nuevo.",
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


def _mapear(resultado: dict, componentes: dict) -> dict:
    return {componentes[nombre]: valor for nombre, valor in resultado.items()}


def _envolver(funcion, componentes: dict):
    if asyncio.iscoroutinefunction(funcion):
        async def envuelta(*argumentos):
            return _mapear(await funcion(*argumentos), componentes)
    else:
        def envuelta(*argumentos):
            return _mapear(funcion(*argumentos), componentes)
    return envuelta


def construir(interfaz: Interfaz) -> gr.Blocks:
    with gr.Blocks(title=TITULO_APP, delete_cache=LIMPIEZA_ARCHIVOS) as demo:
        c: dict[str, Any] = {"sesion": gr.State(None), "conversacion": gr.State(None), "propuesta": gr.State(None)}
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
                c["lista"] = gr.Radio(label="Tus conversaciones", choices=[], value=None)
                c["salir"] = gr.Button("Cerrar sesión", variant="secondary")
            with gr.Column(scale=3):
                c["indicador"] = gr.Markdown("")
                c["chat"] = gr.Chatbot(label="Conversación", height=520, sanitize_html=True)
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
        todo = [c[n] for n in ("sesion", "conversacion", "propuesta", "vista_login", "vista_app", "aviso_login", "clave", "usuario", "chat",
                               "indicador", "lista", "informe", "archivo", "aviso_informe")]
        controles = [c[n] for n in ("entrada", "enviar", "nueva", "salir", "lista")]
        informe_salidas = [c[n] for n in ("informe_destino", "informe_contenido", "aprobar", "rechazar")]
        privado = {"api_visibility": "private"}
        for disparador in (c["entrar"].click, c["clave"].submit):
            disparador(_envolver(interfaz.entrar, c), [c["correo"], c["clave"]], todo, concurrency_limit=CONCURRENCIA_GENERAL, **privado)
        c["salir"].click(_envolver(interfaz.salir, c), [c["sesion"]], todo, **privado)
        c["nueva"].click(_envolver(interfaz.nueva, c), None, [c["conversacion"], c["chat"], c["lista"], c["indicador"], c["propuesta"], c["informe"],
                                                            c["archivo"], c["aviso_informe"]], queue=False, **privado)
        c["lista"].input(_envolver(interfaz.seleccionar, c), [c["sesion"], c["lista"]], todo, concurrency_limit=CONCURRENCIA_GENERAL, **privado)
        for disparador in (c["enviar"].click, c["entrada"].submit):
            (disparador(_envolver(interfaz.bloquear, c), [c["entrada"], c["chat"]], controles + [c["chat"], c["indicador"]], queue=False, **privado)
             .then(_envolver(interfaz.responder, c), [c["sesion"], c["conversacion"], c["entrada"], c["chat"]], todo + [c["entrada"]] + informe_salidas,
                   concurrency_limit=CONCURRENCIA_ATENCION, concurrency_id="atencion", show_progress="minimal", **privado)
             .then(_envolver(interfaz.desbloquear, c), None, controles, queue=False, **privado))
        for boton, manejador in ((c["aprobar"], interfaz.aprobar), (c["rechazar"], interfaz.rechazar)):
            (boton.click(_envolver(interfaz.bloquear_informe, c), None, [c["aprobar"], c["rechazar"]], queue=False, **privado)
             .then(_envolver(manejador, c), [c["sesion"], c["propuesta"]], todo + [c["aprobar"], c["rechazar"]],
                   concurrency_limit=CONCURRENCIA_ATENCION, concurrency_id="atencion", **privado))
    return demo


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
    demo = construir(interfaz)
    demo.queue(default_concurrency_limit=CONCURRENCIA_GENERAL, max_size=MAX_COLA, api_open=False)
    demo.launch(server_name=servidor, server_port=puerto, share=False, show_error=False, footer_links=[])


if __name__ == "__main__":
    main()
