import hashlib
import json
import re
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from postgrest.exceptions import APIError
from supabase import ClientOptions, create_client
from supabase_auth.errors import AuthApiError, AuthError

ROLES = ("usuario", "asistente")
DECISIONES = ("aprobada", "rechazada")
RESULTADOS = ("ejecutada", "fallida")
MAX_TITULO = 120
MAX_CONTENIDO = 20000
MAX_ESTADO = 60
MAX_DESTINO = 300
MAX_CONVERSACIONES = 200
MAX_CORREO, MAX_CLAVE = 320, 200
MAX_LIMITACION, MAX_DETALLE = 2000, 1000
TURNOS_CONTEXTO = 4
PATRON_HUELLA = re.compile(r"^[0-9a-f]{64}$")
PATRON_DESTINO = re.compile(r"^informe_[0-9a-f]{12}\.md$")
PATRON_URL = re.compile(r"^(https://[^\s/]+|http://(127\.0\.0\.1|localhost)(:\d+)?)/?$")
COLUMNAS_MENSAJE = "id,conversacion_id,rol,contenido,estado,fuentes,herramientas,limitacion,detalle_error,propuesta_informe,creado_en,ruta:traza->>ruta"
COLUMNAS_CONVERSACION = "id,usuario_id,titulo,creada_en"
CODIGO_UNICO = "23505"
CODIGOS_ACCESO = {"42501", "23503", "PGRST301", "PGRST302"}


class ErrorAlmacenamiento(Exception):
    pass


class ConfiguracionInvalida(ErrorAlmacenamiento):
    pass


class SesionInvalida(ErrorAlmacenamiento):
    pass


class AccesoDenegado(ErrorAlmacenamiento):
    pass


class DatosInvalidos(ErrorAlmacenamiento):
    pass


class AccionYaRegistrada(ErrorAlmacenamiento):
    pass


class CredencialesInvalidas(ErrorAlmacenamiento):
    pass


class ServicioNoDisponible(ErrorAlmacenamiento):
    pass


@dataclass(frozen=True)
class ConfiguracionSupabase:
    url: str
    clave_publicable: str

    def __post_init__(self):
        if not PATRON_URL.match(self.url or ""):
            raise ConfiguracionInvalida("SUPABASE_URL debe ser la Project URL de Supabase.")
        if not (self.clave_publicable or "").startswith("sb_publishable_"):
            raise ConfiguracionInvalida("SUPABASE_PUBLISHABLE_KEY debe ser una clave publicable; nunca una clave administrativa.")

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str]) -> "ConfiguracionSupabase":
        faltantes = [nombre for nombre in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY") if not (entorno.get(nombre) or "").strip()]
        if faltantes:
            raise ConfiguracionInvalida("Faltan variables de entorno: " + ", ".join(faltantes))
        return cls(entorno["SUPABASE_URL"].strip().rstrip("/"), entorno["SUPABASE_PUBLISHABLE_KEY"].strip())


def crear_cliente(configuracion: ConfiguracionSupabase, token: str):
    opciones = ClientOptions(
        headers={"Authorization": f"Bearer {token}"},
        persist_session=False,
        auto_refresh_token=False,
    )
    return create_client(configuracion.url, configuracion.clave_publicable, options=opciones)


def _uuid(valor: Any, nombre: str) -> str:
    try:
        return str(uuid.UUID(str(valor)))
    except (ValueError, TypeError, AttributeError):
        raise DatosInvalidos(f"{nombre} no es un identificador válido.") from None


def _texto(valor: Any, nombre: str, maximo: int) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise DatosInvalidos(f"{nombre} no puede estar vacío.")
    if len(valor) > maximo:
        raise DatosInvalidos(f"{nombre} supera {maximo} caracteres.")
    return valor


def _texto_opcional(valor: Any, nombre: str, maximo: int) -> str:
    if valor is None:
        return ""
    if not isinstance(valor, str):
        raise DatosInvalidos(f"{nombre} debe ser texto.")
    if len(valor) > maximo:
        raise DatosInvalidos(f"{nombre} supera {maximo} caracteres.")
    return valor


def _propuesta(valor: Any) -> dict | None:
    if valor is None:
        return None
    if not isinstance(valor, Mapping):
        raise DatosInvalidos("La propuesta de informe debe ser un objeto.")
    contenido, huella, destino = valor.get("contenido"), valor.get("huella_contenido"), valor.get("destino")
    _texto(contenido, "El contenido del informe", MAX_CONTENIDO)
    if not isinstance(huella, str) or hashlib.sha256(contenido.encode("utf-8")).hexdigest() != huella:
        raise DatosInvalidos("La huella no corresponde al contenido del informe.")
    if not isinstance(destino, str) or not PATRON_DESTINO.match(destino):
        raise DatosInvalidos("El destino del informe no es válido.")
    return {"contenido": contenido, "huella_contenido": huella, "destino": destino}


def _con_ruta(fila: dict) -> dict:
    traza = fila.pop("traza", None)
    if fila.get("ruta") is None and isinstance(traza, dict):
        fila["ruta"] = traza.get("ruta")
    fila.setdefault("ruta", None)
    return fila


def _lista_json(valor: Any, nombre: str) -> list:
    if valor is None:
        return []
    if not isinstance(valor, Sequence) or isinstance(valor, (str, bytes)):
        raise DatosInvalidos(f"{nombre} debe ser una lista.")
    lista = list(valor)
    try:
        json.dumps(lista, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise DatosInvalidos(f"{nombre} contiene valores que no se pueden guardar.") from None
    return lista


def _objeto_json(valor: Any, nombre: str) -> dict | None:
    if valor is None:
        return None
    if not isinstance(valor, Mapping):
        raise DatosInvalidos(f"{nombre} debe ser un objeto.")
    try:
        return json.loads(json.dumps(dict(valor), ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError):
        raise DatosInvalidos(f"{nombre} contiene valores que no se pueden guardar.") from None


def _error_api(error: APIError, unico: type[ErrorAlmacenamiento] | None = None) -> ErrorAlmacenamiento:
    codigo = str(getattr(error, "code", "") or "")
    if unico is not None and codigo == CODIGO_UNICO:
        return unico("La acción ya estaba registrada.")
    if codigo in CODIGOS_ACCESO:
        return AccesoDenegado("La operación no está autorizada para este usuario.")
    if codigo.startswith("PGRST3"):
        return SesionInvalida("La sesión no es válida o venció.")
    return ErrorAlmacenamiento("Supabase rechazó la operación.")


class Almacenamiento:
    def __init__(self, configuracion: ConfiguracionSupabase, fabrica: Callable[[ConfiguracionSupabase, str], Any] = crear_cliente):
        self._configuracion = configuracion
        self._fabrica = fabrica

    def _abrir(self, token: str):
        if not isinstance(token, str) or not token.strip():
            raise SesionInvalida("No hay una sesión iniciada.")
        cliente = self._fabrica(self._configuracion, token)
        try:
            respuesta = cliente.auth.get_user(token)
        except AuthError:
            raise SesionInvalida("La sesión no es válida o venció.") from None
        usuario = getattr(respuesta, "user", None)
        identificador = getattr(usuario, "id", None)
        if not identificador:
            raise SesionInvalida("La sesión no es válida o venció.")
        return cliente, str(identificador)

    def _ejecutar(self, consulta, unico: type[ErrorAlmacenamiento] | None = None):
        try:
            return consulta.execute().data or []
        except APIError as error:
            raise _error_api(error, unico) from None

    def _conversacion_propia(self, cliente, usuario_id: str, conversacion_id: str) -> dict:
        filas = self._ejecutar(
            cliente.table("conversaciones").select(COLUMNAS_CONVERSACION).eq("id", conversacion_id).eq("usuario_id", usuario_id).limit(1)
        )
        if not filas or filas[0].get("usuario_id") != usuario_id:
            raise AccesoDenegado("La conversación no existe o no pertenece al usuario.")
        return filas[0]

    def usuario(self, token: str) -> str:
        return self._abrir(token)[1]

    def crear_conversacion(self, token: str, titulo: str) -> dict:
        titulo = _texto(titulo, "El título", MAX_TITULO).strip()
        cliente, usuario_id = self._abrir(token)
        filas = self._ejecutar(cliente.table("conversaciones").insert({"usuario_id": usuario_id, "titulo": titulo}))
        if len(filas) != 1:
            raise ErrorAlmacenamiento("Supabase no confirmó la conversación creada.")
        return filas[0]

    def listar_conversaciones(self, token: str, limite: int = MAX_CONVERSACIONES) -> list[dict]:
        if not isinstance(limite, int) or not 1 <= limite <= MAX_CONVERSACIONES:
            raise DatosInvalidos(f"El límite debe estar entre 1 y {MAX_CONVERSACIONES}.")
        cliente, usuario_id = self._abrir(token)
        filas = self._ejecutar(
            cliente.table("conversaciones").select(COLUMNAS_CONVERSACION).eq("usuario_id", usuario_id)
            .order("creada_en", desc=True).order("id", desc=True).limit(limite)
        )
        return [f for f in filas if f.get("usuario_id") == usuario_id]

    def cargar_mensajes(self, token: str, conversacion_id: str, ultimos: int | None = None) -> list[dict]:
        conversacion_id = _uuid(conversacion_id, "La conversación")
        if ultimos is not None and (not isinstance(ultimos, int) or ultimos < 1):
            raise DatosInvalidos("La cantidad de mensajes debe ser positiva.")
        cliente, usuario_id = self._abrir(token)
        self._conversacion_propia(cliente, usuario_id, conversacion_id)
        consulta = cliente.table("mensajes").select(COLUMNAS_MENSAJE).eq("conversacion_id", conversacion_id).eq("usuario_id", usuario_id)
        if ultimos is None:
            filas = self._ejecutar(consulta.order("id"))
        else:
            filas = self._ejecutar(consulta.order("id", desc=True).limit(ultimos))
        return sorted((_con_ruta(dict(f)) for f in filas), key=lambda f: f["id"])

    def cargar_conversacion(self, token: str, conversacion_id: str) -> tuple[list[dict], dict[int, dict]]:
        conversacion_id = _uuid(conversacion_id, "La conversación")
        cliente, usuario_id = self._abrir(token)
        mensajes = [f for f in self._ejecutar(
            cliente.table("mensajes").select(COLUMNAS_MENSAJE + ",usuario_id").eq("conversacion_id", conversacion_id).eq("usuario_id", usuario_id).order("id")
        ) if f.get("usuario_id") == usuario_id]
        if not mensajes:
            self._conversacion_propia(cliente, usuario_id, conversacion_id)
            return [], {}
        decisiones: dict[int, dict] = {}
        if any(f.get("propuesta_informe") for f in mensajes):
            acciones = self._ejecutar(
                cliente.table("acciones_informe").select("id,mensaje_id,usuario_id,decision,resultado,destino")
                .eq("conversacion_id", conversacion_id).eq("usuario_id", usuario_id)
            )
            decisiones = {f["mensaje_id"]: f for f in acciones if f.get("usuario_id") == usuario_id}
        return sorted((_con_ruta({k: v for k, v in f.items() if k != "usuario_id"}) for f in mensajes), key=lambda f: f["id"]), decisiones

    def ventana_contexto(self, token: str, conversacion_id: str, turnos: int = TURNOS_CONTEXTO) -> list[dict]:
        if not isinstance(turnos, int) or turnos < 1:
            raise DatosInvalidos("La ventana debe tener al menos un turno.")
        return self.cargar_mensajes(token, conversacion_id, ultimos=turnos * 2)

    def guardar_turno(
        self,
        token: str,
        conversacion_id: str,
        pregunta: str,
        respuesta: str,
        estado: str,
        fuentes: Sequence[Mapping[str, Any]] | None = None,
        herramientas: Sequence[Mapping[str, Any]] | None = None,
        traza: Mapping[str, Any] | None = None,
        limitacion: str | None = "",
        detalle_error: str | None = "",
        propuesta_informe: Mapping[str, Any] | None = None,
    ) -> tuple[dict, dict]:
        conversacion_id = _uuid(conversacion_id, "La conversación")
        pregunta = _texto(pregunta, "La pregunta", MAX_CONTENIDO)
        respuesta = _texto(respuesta, "La respuesta", MAX_CONTENIDO)
        estado = _texto(estado, "El estado", MAX_ESTADO)
        fuentes = _lista_json(fuentes, "Las fuentes")
        herramientas = _lista_json(herramientas, "Las herramientas")
        traza = _objeto_json(traza, "La traza")
        limitacion = _texto_opcional(limitacion, "La limitación", MAX_LIMITACION)
        detalle_error = _texto_opcional(detalle_error, "El detalle del error", MAX_DETALLE)
        propuesta_informe = _propuesta(propuesta_informe)
        cliente, usuario_id = self._abrir(token)
        self._conversacion_propia(cliente, usuario_id, conversacion_id)
        filas = [
            {"conversacion_id": conversacion_id, "usuario_id": usuario_id, "rol": "usuario", "contenido": pregunta,
             "estado": None, "fuentes": [], "herramientas": [], "traza": None, "limitacion": "", "detalle_error": "",
             "propuesta_informe": None},
            {"conversacion_id": conversacion_id, "usuario_id": usuario_id, "rol": "asistente", "contenido": respuesta,
             "estado": estado, "fuentes": fuentes, "herramientas": herramientas, "traza": traza,
             "limitacion": limitacion, "detalle_error": detalle_error, "propuesta_informe": propuesta_informe},
        ]
        guardadas = sorted(self._ejecutar(cliente.table("mensajes").insert(filas)), key=lambda f: f["id"])
        if [f.get("rol") for f in guardadas] != list(ROLES):
            raise ErrorAlmacenamiento("Supabase no confirmó el turno completo.")
        return guardadas[0], guardadas[1]

    def registrar_decision_informe(
        self,
        token: str,
        conversacion_id: str,
        mensaje_id: int,
        decision: str,
        destino: str,
        huella_contenido: str,
    ) -> dict:
        conversacion_id = _uuid(conversacion_id, "La conversación")
        if not isinstance(mensaje_id, int) or isinstance(mensaje_id, bool) or mensaje_id < 1:
            raise DatosInvalidos("El mensaje no es válido.")
        if decision not in DECISIONES:
            raise DatosInvalidos("La decisión debe ser aprobada o rechazada.")
        destino = _texto(destino, "El destino", MAX_DESTINO)
        if not isinstance(huella_contenido, str) or not PATRON_HUELLA.match(huella_contenido):
            raise DatosInvalidos("La huella del contenido debe ser un SHA-256 en hexadecimal.")
        cliente, usuario_id = self._abrir(token)
        self._conversacion_propia(cliente, usuario_id, conversacion_id)
        mensaje = self._ejecutar(
            cliente.table("mensajes").select("id,rol").eq("id", mensaje_id).eq("conversacion_id", conversacion_id).limit(1)
        )
        if not mensaje or mensaje[0].get("rol") != "asistente":
            raise AccesoDenegado("El mensaje no pertenece a la conversación.")
        filas = self._ejecutar(
            cliente.table("acciones_informe").insert({
                "conversacion_id": conversacion_id, "usuario_id": usuario_id, "mensaje_id": mensaje_id,
                "decision": decision, "destino": destino, "huella_contenido": huella_contenido,
            }),
            unico=AccionYaRegistrada,
        )
        if len(filas) != 1:
            raise ErrorAlmacenamiento("Supabase no confirmó la decisión.")
        return filas[0]

    def obtener_accion_informe(self, token: str, accion_id: str) -> dict:
        accion_id = _uuid(accion_id, "La acción")
        cliente, usuario_id = self._abrir(token)
        filas = self._ejecutar(
            cliente.table("acciones_informe").select("id,conversacion_id,usuario_id,mensaje_id,decision,resultado,destino,huella_contenido,creada_en")
            .eq("id", accion_id).eq("usuario_id", usuario_id).limit(1)
        )
        if not filas or filas[0].get("usuario_id") != usuario_id:
            raise AccesoDenegado("La acción no existe o no pertenece al usuario.")
        return filas[0]

    def decisiones_informe(self, token: str, conversacion_id: str) -> dict[int, dict]:
        conversacion_id = _uuid(conversacion_id, "La conversación")
        cliente, usuario_id = self._abrir(token)
        self._conversacion_propia(cliente, usuario_id, conversacion_id)
        filas = self._ejecutar(
            cliente.table("acciones_informe").select("id,mensaje_id,usuario_id,decision,resultado,destino")
            .eq("conversacion_id", conversacion_id).eq("usuario_id", usuario_id)
        )
        return {f["mensaje_id"]: f for f in filas if f.get("usuario_id") == usuario_id}

    def registrar_resultado_informe(self, token: str, accion_id: str, resultado: str) -> dict:
        accion_id = _uuid(accion_id, "La acción")
        if resultado not in RESULTADOS:
            raise DatosInvalidos("El resultado debe ser ejecutada o fallida.")
        cliente, usuario_id = self._abrir(token)
        filas = self._ejecutar(
            cliente.table("acciones_informe").update({"resultado": resultado})
            .eq("id", accion_id).eq("usuario_id", usuario_id).eq("decision", "aprobada").is_("resultado", "null")
        )
        if len(filas) != 1:
            raise AccionYaRegistrada("La acción no existe, no fue aprobada o ya tenía resultado.")
        return filas[0]


def crear_cliente_autenticacion(configuracion: ConfiguracionSupabase):
    opciones = ClientOptions(persist_session=False, auto_refresh_token=False)
    return create_client(configuracion.url, configuracion.clave_publicable, options=opciones)


@dataclass(frozen=True)
class Sesion:
    access_token: str
    refresh_token: str
    expira_en: float
    usuario_id: str
    correo: str

    def como_estado(self) -> dict:
        return {"access_token": self.access_token, "refresh_token": self.refresh_token, "expira_en": self.expira_en,
                "usuario_id": self.usuario_id, "correo": self.correo}


def _sesion_desde(respuesta: Any) -> Sesion:
    sesion = getattr(respuesta, "session", None)
    usuario = getattr(respuesta, "user", None) or getattr(sesion, "user", None)
    if not sesion or not getattr(sesion, "access_token", None) or not getattr(sesion, "refresh_token", None) or not getattr(usuario, "id", None):
        raise SesionInvalida("El servicio de autenticación no devolvió una sesión.")
    expira = getattr(sesion, "expires_at", None) or time.time() + (getattr(sesion, "expires_in", None) or 3600)
    return Sesion(sesion.access_token, sesion.refresh_token, float(expira), str(usuario.id), str(getattr(usuario, "email", "") or ""))


class Autenticacion:
    def __init__(self, configuracion: ConfiguracionSupabase, fabrica: Callable[[ConfiguracionSupabase], Any] = crear_cliente_autenticacion):
        self._configuracion = configuracion
        self._fabrica = fabrica

    def iniciar_sesion(self, correo: str, clave: str) -> Sesion:
        if not isinstance(correo, str) or not isinstance(clave, str) or not correo.strip() or not clave:
            raise CredencialesInvalidas("Escribe el correo y la contraseña.")
        if len(correo) > MAX_CORREO or len(clave) > MAX_CLAVE:
            raise CredencialesInvalidas("El correo o la contraseña son demasiado largos.")
        try:
            respuesta = self._fabrica(self._configuracion).auth.sign_in_with_password({"email": correo.strip(), "password": clave})
        except AuthApiError as error:
            if getattr(error, "status", None) == 429:
                raise ServicioNoDisponible("Demasiados intentos de inicio de sesión; espera unos minutos.") from None
            if getattr(error, "status", None) and error.status >= 500:
                raise ServicioNoDisponible("El servicio de autenticación no respondió; intenta de nuevo.") from None
            raise CredencialesInvalidas("No se pudo iniciar sesión: revisa el correo y la contraseña.") from None
        except AuthError:
            raise ServicioNoDisponible("El servicio de autenticación no respondió; intenta de nuevo.") from None
        except Exception:
            raise ServicioNoDisponible("No fue posible conectar con el servicio de autenticación.") from None
        return _sesion_desde(respuesta)

    def refrescar(self, refresh_token: str) -> Sesion:
        if not isinstance(refresh_token, str) or not refresh_token.strip():
            raise SesionInvalida("No hay una sesión para renovar.")
        try:
            respuesta = self._fabrica(self._configuracion).auth.refresh_session(refresh_token)
        except Exception:
            raise SesionInvalida("La sesión venció y no se pudo renovar.") from None
        return _sesion_desde(respuesta)

    def cerrar_sesion(self, access_token: str, refresh_token: str) -> None:
        try:
            cliente = self._fabrica(self._configuracion)
            cliente.auth.set_session(access_token, refresh_token)
            cliente.auth.sign_out({"scope": "local"})
        except Exception:
            return
