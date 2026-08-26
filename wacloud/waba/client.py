"""Suscripción de la app a una WABA y datos de la cuenta.

**Sin suscribir la app a una WABA, Meta no entrega ni un solo webhook de esa cuenta.**
Con una única WABA se hace una vez a mano en el panel; en multiempresa, donde cada
empresa trae la suya, tiene que ser programático o no hay onboarding posible.

Es alcance **WABA**, no número: por eso vive aparte de ``NumbersClient``. Comparte con él
el límite de la Business Management API — 200 peticiones por hora y WABA, 5.000 si la
WABA tiene un número registrado (código ``80008``).

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks
"""

from __future__ import annotations

from typing import Any

from wacloud.credentials import CredentialResolver
from wacloud.transport import Transport
from wacloud.waba.models import SubscribedApp, WabaInfo

#: Campos que se piden al consultar la WABA. Meta devuelve un subconjunto mínimo si no
#: se especifican, así que se enumeran para obtener siempre lo mismo.
_WABA_FIELDS = (
    "id",
    "name",
    "timezone_id",
    "currency",
    "account_review_status",
    "message_template_namespace",
)

_SUBSCRIBED_APPS = "subscribed_apps"


class WabaClient:
    """Suscripción de webhooks y metadatos de una WhatsApp Business Account."""

    def __init__(self, transport: Transport, resolver: CredentialResolver) -> None:
        self._transport = transport
        self._resolver = resolver

    async def get(self, waba_id: str) -> WabaInfo:
        """Datos de la WABA: nombre, zona horaria, moneda y estado de revisión.

        ``account_review_status`` es lo que dice si Meta aprobó la cuenta. Conviene
        mirarlo antes de dar por terminado el alta de una empresa: una WABA sin aprobar
        acepta configuración pero no entrega mensajes en producción.
        """
        credentials = await self._resolver.for_waba_id(waba_id)
        response = await self._transport.request(
            "GET",
            f"/{waba_id}",
            access_token=credentials.access_token,
            params={"fields": ",".join(_WABA_FIELDS)},
        )
        return WabaInfo.from_meta(response)

    async def subscribe(
        self,
        waba_id: str,
        *,
        override_callback_uri: str | None = None,
        verify_token: str | None = None,
    ) -> bool:
        """Suscribe la app a los webhooks de esta WABA.

        Sin esto Meta no entrega **ningún** webhook de la cuenta, ni de mensajes ni de
        plantillas. Es idempotente: repetirla sobre una WABA ya suscrita devuelve éxito.

        ``override_callback_uri`` declara un callback propio **para esta WABA**, distinto
        del que tenga configurado la app. En multiempresa permite que cada cuenta entregue
        a su propia URL sin montar una app de Meta por empresa. Si se usa, Meta exige
        también ``verify_token``, y lanzará contra esa URL la misma verificación ``GET``
        con ``hub.challenge`` que hace al dar de alta un webhook normal
        (ver ``wacloud.webhook.verify_subscription``).
        """
        if override_callback_uri and not verify_token:
            raise ValueError(
                "'override_callback_uri' exige 'verify_token': Meta verifica esa URL "
                "con un GET de hub.challenge antes de aceptarla"
            )
        if verify_token and not override_callback_uri:
            raise ValueError("'verify_token' solo aplica junto a 'override_callback_uri'")

        params: dict[str, Any] = {}
        if override_callback_uri:
            params["override_callback_uri"] = override_callback_uri
            params["verify_token"] = verify_token

        credentials = await self._resolver.for_waba_id(waba_id)
        response = await self._transport.request(
            "POST",
            f"/{waba_id}/{_SUBSCRIBED_APPS}",
            access_token=credentials.access_token,
            params=params or None,
        )
        return bool(response.get("success", False))

    async def list_subscriptions(self, waba_id: str) -> list[SubscribedApp]:
        """Apps suscritas a esta WABA.

        Es la mitad del soporte de este flujo: cuando un webhook no llega, lo primero es
        saber si la suscripción quedó hecha y a qué URL apunta.
        """
        credentials = await self._resolver.for_waba_id(waba_id)
        response = await self._transport.request(
            "GET",
            f"/{waba_id}/{_SUBSCRIBED_APPS}",
            access_token=credentials.access_token,
        )
        data = response.get("data")
        if not isinstance(data, list):
            return []
        return [SubscribedApp.from_meta(i) for i in data if isinstance(i, dict)]

    async def unsubscribe(self, waba_id: str) -> bool:
        """Da de baja la app de los webhooks de esta WABA.

        Deja de llegar todo lo de esa cuenta de inmediato. En multiempresa es lo que se
        ejecuta al desconectar a un cliente: sin esto sus webhooks siguen entrando y el
        host recibe tráfico de alguien a quien ya no sirve.
        """
        credentials = await self._resolver.for_waba_id(waba_id)
        response = await self._transport.request(
            "DELETE",
            f"/{waba_id}/{_SUBSCRIBED_APPS}",
            access_token=credentials.access_token,
        )
        return bool(response.get("success", False))
