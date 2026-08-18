"""Modelos de la información y el perfil de un número.

Los campos enumerados se guardan como ``str`` y no como ``Enum`` a propósito: las dos
generaciones de documentación de Meta discrepan en la ortografía de varios valores, y un
enum estricto haría fallar el parseo ante algo que Meta considera correcto. Para comparar
están las constantes de ``wacloud.numbers.enums``.

Todos llevan ``raw`` con la respuesta íntegra: si Meta añade un campo, el host puede
leerlo sin esperar a que la librería lo modele.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PhoneNumberInfo(BaseModel):
    """Estado y metadatos de un número de la WABA."""

    id: str | None = None
    display_phone_number: str | None = None
    verified_name: str | None = None
    #: ``GREEN`` | ``YELLOW`` | ``RED`` | ``NA`` | ``UNKNOWN``.
    quality_rating: str | None = None
    #: ``CONNECTED`` | ``FLAGGED`` | ``RESTRICTED``…
    status: str | None = None
    code_verification_status: str | None = None
    name_status: str | None = None
    #: ``SANDBOX`` limita a destinatarios de prueba.
    account_mode: str | None = None
    is_official_business_account: bool | None = None
    #: Límite de mensajería del portfolio (``TIER_250``, ``TIER_2K``…).
    #:
    #: Viene de ``whatsapp_business_manager_messaging_limit``. El campo antiguo
    #: ``messaging_limit_tier`` está deprecado y se lee como respaldo.
    messaging_limit: str | None = None
    #: Mensajes por segundo. Meta dejó de publicar la forma de este campo, así que se
    #: acepta tanto un número suelto como el objeto ``{"level": ...}`` que usaba antes.
    throughput: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_meta(cls, item: dict[str, Any]) -> PhoneNumberInfo:
        return cls(
            id=_as_str(item.get("id")),
            display_phone_number=item.get("display_phone_number"),
            verified_name=item.get("verified_name"),
            quality_rating=item.get("quality_rating"),
            status=item.get("status"),
            code_verification_status=item.get("code_verification_status"),
            name_status=item.get("name_status"),
            account_mode=item.get("account_mode"),
            is_official_business_account=item.get("is_official_business_account"),
            messaging_limit=_as_str(
                item.get("whatsapp_business_manager_messaging_limit")
                or item.get("messaging_limit_tier")
            ),
            throughput=_throughput(item.get("throughput")),
            raw=item,
        )

    @property
    def is_connected(self) -> bool:
        return self.status == "CONNECTED"

    @property
    def is_verified(self) -> bool:
        return self.code_verification_status == "VERIFIED"


class BusinessProfile(BaseModel):
    """Perfil público que ven los usuarios al abrir el chat.

    Asimetría de Meta que conviene tener presente: se **lee** ``profile_picture_url`` pero
    se **escribe** ``profile_picture_handle``, que sale de la Resumable Upload API.
    """

    about: str | None = None
    address: str | None = None
    description: str | None = None
    email: str | None = None
    vertical: str | None = None
    websites: list[str] = Field(default_factory=list)
    #: Solo de lectura.
    profile_picture_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_meta(cls, body: dict[str, Any]) -> BusinessProfile:
        """Extrae el perfil de la respuesta.

        Meta lo devuelve envuelto en una lista bajo ``data`` aunque solo haya uno.
        """
        data = body.get("data")
        item = data[0] if isinstance(data, list) and data else body
        if not isinstance(item, dict):
            item = {}
        websites = item.get("websites")
        return cls(
            about=item.get("about"),
            address=item.get("address"),
            description=item.get("description"),
            email=item.get("email"),
            vertical=item.get("vertical"),
            websites=[w for w in websites if isinstance(w, str)]
            if isinstance(websites, list)
            else [],
            profile_picture_url=item.get("profile_picture_url"),
            raw=item,
        )


def _as_str(value: Any) -> str | None:
    """Meta devuelve algunos identificadores como número y otros como cadena."""
    if value is None:
        return None
    return str(value)


def _throughput(value: Any) -> str | None:
    """Normaliza ``throughput``, que Meta ha devuelto con dos formas distintas.

    En versiones antiguas era ``{"level": "STANDARD"}``; los ejemplos actuales muestran un
    entero de mensajes por segundo. La referencia vigente ya no publica su forma, así que
    se aceptan ambas y se devuelve cadena.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        level = value.get("level")
        return str(level) if level is not None else None
    return str(value)
