"""Modelos de la WABA y de sus suscripciones de webhook.

Como en el resto de la librería, los campos enumerados se guardan como ``str`` y no como
``Enum``: Meta añade estados de revisión sin avisar y un enum estricto convertiría eso en
una excepción en producción. Ver la sección "estricto al construir, permisivo al parsear"
del CLAUDE.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WabaInfo(BaseModel):
    """Datos de una WhatsApp Business Account.

    ``account_review_status`` es lo que dice si Meta aprobó la cuenta: sin ``APPROVED``
    la WABA existe pero no puede mensajear en producción, así que es el primer campo que
    hay que mirar al dar de alta una empresa.
    """

    id: str | None = None
    name: str | None = None
    #: Identificador de zona horaria de Meta, no un nombre IANA.
    timezone_id: str | None = None
    currency: str | None = None
    #: ``APPROVED`` | ``PENDING`` | ``REJECTED``…
    account_review_status: str | None = None
    #: Prefijo de las plantillas de esta WABA. Necesario en la API On-Premises; en Cloud
    #: API rara vez hace falta, pero Meta lo sigue devolviendo.
    message_template_namespace: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_meta(cls, item: dict[str, Any]) -> WabaInfo:
        return cls(
            id=_as_str(item.get("id")),
            name=item.get("name"),
            timezone_id=_as_str(item.get("timezone_id")),
            currency=item.get("currency"),
            account_review_status=item.get("account_review_status"),
            message_template_namespace=item.get("message_template_namespace"),
            raw=item,
        )

    @property
    def is_approved(self) -> bool:
        return self.account_review_status == "APPROVED"


class SubscribedApp(BaseModel):
    """Una app suscrita a los webhooks de una WABA.

    ``override_callback_uri`` solo viene si esa app declaró un callback propio para esta
    WABA. En multiempresa es el campo que permite comprobar que cada cuenta apunta a
    donde debe.
    """

    app_id: str | None = None
    name: str | None = None
    link: str | None = None
    override_callback_uri: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_meta(cls, item: dict[str, Any]) -> SubscribedApp:
        """Meta anida los datos de la app bajo ``whatsapp_business_api_data``."""
        data = item.get("whatsapp_business_api_data")
        app = data if isinstance(data, dict) else {}
        return cls(
            app_id=_as_str(app.get("id")),
            name=app.get("name"),
            link=app.get("link"),
            override_callback_uri=_as_str(item.get("override_callback_uri")),
            raw=item,
        )


class BusinessToken(BaseModel):
    """Token de negocio obtenido al canjear el código de Embedded Signup.

    Meta no devuelve ``expires_in`` para los tokens de sistema de un negocio: son de
    larga duración y por eso el campo llega vacío casi siempre. Guardarlo cifrado y
    tratarlo como permanente hasta que Meta responda ``190`` es lo esperado.
    """

    access_token: str
    token_type: str | None = None
    expires_in: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_meta(cls, body: dict[str, Any]) -> BusinessToken:
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError(f"Meta no devolvió un access_token: {body!r}")
        expires = body.get("expires_in")
        return cls(
            access_token=token,
            token_type=_as_str(body.get("token_type")),
            expires_in=expires if isinstance(expires, int) else None,
            raw=body,
        )


def _as_str(value: Any) -> str | None:
    """Meta devuelve algunos identificadores como número y otros como cadena."""
    if value is None:
        return None
    return str(value)
