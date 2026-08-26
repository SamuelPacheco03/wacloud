"""Canje del código de Embedded Signup por un token de negocio.

Embedded Signup es el flujo en el que un cliente conecta su propia WABA desde un popup
de Meta. Al terminar, el navegador devuelve un ``code`` de un solo uso que hay que
canjear en el servidor por el token con el que se opera esa cuenta.

Vive en la raíz y no dentro de ``waba/`` porque es alcance **de app**, no de WABA: usa
``app_id`` y ``app_secret``, no un token de negocio, y ocurre antes de que exista
ninguna WABA que consultar.

Por qué está en la librería y no en el host: si no, cada consumidor reimplementa el
canje, y con él las reglas de Meta que lo rodean —el código caduca, es de un solo uso, y
el token que devuelve no es el mismo tipo de token que el de un número—. La razón de ser
de wacloud es que esas reglas vivan en un sitio.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup
"""

from __future__ import annotations

from wacloud.transport import Transport
from wacloud.waba.models import BusinessToken

_OAUTH_PATH = "/oauth/access_token"


class OAuthClient:
    """Intercambio del código de Embedded Signup por un token de negocio.

    No recibe un ``CredentialResolver``: en este punto todavía no hay número ni WABA que
    resolver. Las credenciales son las de la app de Meta y se pasan al construirlo.

    **El ``app_secret`` viaja en la query string**, porque así lo define Meta para este
    endpoint. Eso significa que puede acabar en los logs de acceso de cualquier proxy
    intermedio: no expongas este canje a través de nada que registre URLs completas, y
    no lo reenvíes desde un frontend.
    """

    def __init__(self, transport: Transport, *, app_id: str, app_secret: str) -> None:
        if not str(app_id or "").strip():
            raise ValueError("app_id es obligatorio")
        if not str(app_secret or "").strip():
            raise ValueError("app_secret es obligatorio")
        self._transport = transport
        self._app_id = str(app_id).strip()
        self._app_secret = str(app_secret).strip()

    async def exchange_code(self, code: str) -> BusinessToken:
        """Canjea el ``code`` de Embedded Signup por el token de negocio.

        El código es de **un solo uso** y caduca en minutos: si el canje falla por red,
        reintentarlo con el mismo código no va a funcionar y hay que rehacer el flujo del
        popup. Por eso la petición se marca como no idempotente — el transporte solo la
        repetirá cuando Meta haya rechazado de forma reconocible, nunca ante un timeout.

        El token que devuelve es de larga duración y es el que se guarda cifrado para
        operar la WABA del cliente. Tras obtenerlo, el alta no está completa: falta
        suscribir la app a la WABA (``WabaClient.subscribe``) o no llegará ningún webhook.
        """
        clean = str(code or "").strip()
        if not clean:
            raise ValueError("el código de Embedded Signup es obligatorio")

        response = await self._transport.request(
            "GET",
            _OAUTH_PATH,
            access_token=None,
            params={
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "code": clean,
            },
            idempotent=False,
        )
        return BusinessToken.from_meta(response)
