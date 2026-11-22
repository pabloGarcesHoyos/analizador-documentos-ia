import copy
import itertools
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError


def _ahora():
    return datetime.now(timezone.utc).isoformat()


class BaseFalsa:
    def __init__(self, usuarios):
        self.usuarios = dict(usuarios)
        self.tablas = {"conversaciones": [], "mensajes": [], "acciones_informe": []}
        self.secuencia = itertools.count(1)
        self.tokens_usados = []
        self.consultas_get_user = 0

    def fabrica(self, configuracion, token):
        self.tokens_usados.append(token)
        return ClienteFalso(self, token)

    def visible(self, tabla, fila, uid):
        if uid is None:
            return False
        if tabla == "conversaciones":
            return fila["usuario_id"] == uid
        if tabla == "mensajes":
            return fila["usuario_id"] == uid and self._conversacion_de(fila["conversacion_id"], uid)
        return fila["usuario_id"] == uid

    def _conversacion_de(self, conversacion_id, uid):
        return any(c["id"] == conversacion_id and c["usuario_id"] == uid for c in self.tablas["conversaciones"])

    def insertar(self, tabla, fila, uid):
        fila = copy.deepcopy(fila)
        fila.setdefault("usuario_id", uid)
        if uid is None or fila["usuario_id"] != uid:
            raise APIError({"code": "42501", "message": "new row violates row-level security policy"})
        if tabla == "conversaciones":
            fila.setdefault("id", str(uuid.uuid4()))
            fila.setdefault("creada_en", _ahora())
        elif tabla == "mensajes":
            if not any(c["id"] == fila["conversacion_id"] for c in self.tablas["conversaciones"]):
                raise APIError({"code": "23503", "message": "foreign key violation"})
            if not self._conversacion_de(fila["conversacion_id"], uid):
                raise APIError({"code": "42501", "message": "new row violates row-level security policy"})
            fila["id"] = next(self.secuencia)
            fila.setdefault("creado_en", _ahora())
        elif tabla == "acciones_informe":
            if not self._conversacion_de(fila["conversacion_id"], uid):
                raise APIError({"code": "42501", "message": "new row violates row-level security policy"})
            if any(a["usuario_id"] == uid and a["mensaje_id"] == fila["mensaje_id"] for a in self.tablas["acciones_informe"]):
                raise APIError({"code": "23505", "message": "duplicate key value violates unique constraint"})
            fila.setdefault("id", str(uuid.uuid4()))
            fila.setdefault("resultado", None)
            fila.setdefault("creada_en", _ahora())
        return fila


class AuthFalsa:
    def __init__(self, base):
        self.base = base

    def get_user(self, jwt=None):
        self.base.consultas_get_user += 1
        uid = self.base.usuarios.get(jwt)
        if uid is None:
            raise AuthApiError("invalid JWT", 401, "bad_jwt")
        return SimpleNamespace(user=SimpleNamespace(id=uid))


class ClienteFalso:
    def __init__(self, base, token):
        self.base = base
        self.uid = base.usuarios.get(token)
        self.auth = AuthFalsa(base)

    def table(self, nombre):
        return ConsultaFalsa(self.base, nombre, self.uid)


class ConsultaFalsa:
    def __init__(self, base, tabla, uid):
        self.base = base
        self.tabla = tabla
        self.uid = uid
        self.filtros = []
        self.orden = []
        self.tope = None
        self.operacion = "select"
        self.datos = None

    def select(self, columnas="*"):
        self.operacion = "select"
        return self

    def insert(self, datos):
        self.operacion = "insert"
        self.datos = datos
        return self

    def update(self, datos):
        self.operacion = "update"
        self.datos = datos
        return self

    def eq(self, columna, valor):
        self.filtros.append(lambda f: f.get(columna) == valor)
        return self

    def is_(self, columna, valor):
        self.filtros.append(lambda f: f.get(columna) is None if valor == "null" else f.get(columna) == valor)
        return self

    def order(self, columna, desc=False):
        self.orden.append((columna, desc))
        return self

    def limit(self, cantidad):
        self.tope = cantidad
        return self

    def _seleccion(self):
        filas = [f for f in self.base.tablas[self.tabla] if self.base.visible(self.tabla, f, self.uid)]
        filas = [f for f in filas if all(filtro(f) for filtro in self.filtros)]
        for columna, desc in reversed(self.orden):
            filas.sort(key=lambda f: f[columna], reverse=desc)
        return filas[: self.tope] if self.tope is not None else filas

    def execute(self):
        if self.operacion == "insert":
            nuevas = [self.base.insertar(self.tabla, f, self.uid) for f in (self.datos if isinstance(self.datos, list) else [self.datos])]
            self.base.tablas[self.tabla].extend(nuevas)
            return SimpleNamespace(data=copy.deepcopy(nuevas))
        if self.operacion == "update":
            filas = self._seleccion()
            if self.tabla == "acciones_informe":
                filas = [f for f in filas if f["decision"] == "aprobada" and f["resultado"] is None]
            for fila in filas:
                fila.update(self.datos)
            return SimpleNamespace(data=copy.deepcopy(filas))
        return SimpleNamespace(data=copy.deepcopy(self._seleccion()))
