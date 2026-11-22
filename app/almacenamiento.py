import json
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from postgrest.exceptions import APIError
from supabase import ClientOptions, create_client
from supabase_auth.errors import AuthError

ROLES = ("usuario", "asistente")
DECISIONES = ("aprobada", "rechazada")
RESULTADOS = ("ejecutada", "fallida")
MAX_TITULO = 120
MAX_CONTENIDO = 20000
MAX_ESTADO = 60
MAX_DESTINO = 300
MAX_CONVERSACIONES = 200
TURNOS_CONTEXTO = 4
PATRON_HUELLA = re.compile(r"^[0-9a-f]{64}$")
PATRON_URL = re.compile(r"^(https://[^\s/]+|http://(127\.0\.0\.1|localhost)(:\d+)?)/?$")
COLUMNAS_MENSAJE = "id,conversacion_id,rol,contenido,estado,fuentes,herramientas,creado_en"
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
        return sorted(filas, key=lambda f: f["id"])

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
    ) -> tuple[dict, dict]:
        conversacion_id = _uuid(conversacion_id, "La conversación")
        pregunta = _texto(pregunta, "La pregunta", MAX_CONTENIDO)
        respuesta = _texto(respuesta, "La respuesta", MAX_CONTENIDO)
        estado = _texto(estado, "El estado", MAX_ESTADO)
        fuentes = _lista_json(fuentes, "Las fuentes")
        herramientas = _lista_json(herramientas, "Las herramientas")
        traza = _objeto_json(traza, "La traza")
        cliente, usuario_id = self._abrir(token)
        self._conversacion_propia(cliente, usuario_id, conversacion_id)
        filas = [
            {"conversacion_id": conversacion_id, "usuario_id": usuario_id, "rol": "usuario", "contenido": pregunta,
             "estado": None, "fuentes": [], "herramientas": [], "traza": None},
            {"conversacion_id": conversacion_id, "usuario_id": usuario_id, "rol": "asistente", "contenido": respuesta,
             "estado": estado, "fuentes": fuentes, "herramientas": herramientas, "traza": traza},
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
