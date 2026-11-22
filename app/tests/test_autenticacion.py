from types import SimpleNamespace

import pytest
from supabase_auth.errors import AuthApiError, AuthRetryableError

import almacenamiento as al


class ClienteAuthFalso:
    def __init__(self, error=None):
        self.error = error
        self.auth = self
        self.llamadas = []

    def _responder(self):
        if self.error:
            raise self.error
        usuario = SimpleNamespace(id="u-1", email="a@prueba.local")
        return SimpleNamespace(user=usuario, session=SimpleNamespace(access_token="acceso", refresh_token="renovacion", expires_at=2000, user=usuario))

    def sign_in_with_password(self, credenciales):
        self.llamadas.append("inicio")
        return self._responder()

    def refresh_session(self, renovacion):
        self.llamadas.append(("renovar", renovacion))
        return self._responder()

    def set_session(self, acceso, renovacion):
        self.llamadas.append("fijar")

    def sign_out(self, opciones):
        self.llamadas.append(("salir", opciones["scope"]))


CONFIG_SUPABASE = al.ConfiguracionSupabase("https://p.supabase.co", "sb_publishable_x")


@pytest.mark.parametrize("error, clase", [
    (AuthApiError("Invalid login credentials", 400, "invalid_credentials"), al.CredencialesInvalidas),
    (AuthApiError("Too many requests", 429, "over_request_rate_limit"), al.ServicioNoDisponible),
    (AuthRetryableError("caído", 503), al.ServicioNoDisponible),
    (ConnectionError("sin red"), al.ServicioNoDisponible),
])
def test_autenticacion_clasifica_los_errores_sin_exponer_la_clave(error, clase):
    autenticacion = al.Autenticacion(CONFIG_SUPABASE, fabrica=lambda configuracion: ClienteAuthFalso(error))
    with pytest.raises(clase) as capturado:
        autenticacion.iniciar_sesion("a@prueba.local", "clave-muy-secreta")
    assert "clave-muy-secreta" not in str(capturado.value) and capturado.value.__cause__ is None


def test_autenticacion_crea_un_cliente_por_operacion():
    clientes = []

    def fabrica(configuracion):
        clientes.append(ClienteAuthFalso())
        return clientes[-1]

    autenticacion = al.Autenticacion(CONFIG_SUPABASE, fabrica=fabrica)
    sesion = autenticacion.iniciar_sesion(" a@prueba.local ", "clave")
    assert (sesion.access_token, sesion.refresh_token, sesion.expira_en, sesion.usuario_id) == ("acceso", "renovacion", 2000.0, "u-1")
    autenticacion.refrescar("renovacion")
    autenticacion.cerrar_sesion("acceso", "renovacion")
    assert [c.llamadas for c in clientes] == [["inicio"], [("renovar", "renovacion")], ["fijar", ("salir", "local")]]
    with pytest.raises(al.CredencialesInvalidas):
        autenticacion.iniciar_sesion("a@prueba.local", "")
    with pytest.raises(al.SesionInvalida):
        al.Autenticacion(CONFIG_SUPABASE, fabrica=lambda c: ClienteAuthFalso(AuthApiError("Invalid Refresh Token", 400, None))).refrescar("vieja")
