"""Eventos normalizados que produce el parser del webhook.

Solo estructuras de datos: sin lógica de extracción y sin red. Es lo que el host
consume, así que su forma es la superficie estable de esta parte de la librería.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Tipos de mensaje que traen un medio adjunto.
MEDIA_TYPES = ("image", "audio", "video", "document", "sticker")


@dataclass(frozen=True)
class InboundMedia:
    """Referencia al medio de un mensaje entrante, sin descargar.

    Se agrupa en su propio objeto en vez de aplanarlo en ``WebhookInboundMessage``
    para que el host distinga "mensaje sin medio" de "medio con campos vacíos".
    """

    media_id: str | None = None
    mime_type: str | None = None
    filename: str | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class InboundLocation:
    """Ubicación compartida por el usuario.

    A diferencia del envío, donde Meta documenta las coordenadas como cadena, en el
    webhook llegan como números.
    """

    latitude: float | None = None
    longitude: float | None = None
    name: str | None = None
    address: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class InboundReaction:
    """Reacción a un mensaje anterior.

    ``emoji`` a ``None`` significa que el usuario **retiró** la reacción: Meta omite el
    campo por completo en ese caso, y es la forma documentada de detectarlo.
    """

    message_id: str
    emoji: str | None = None

    @property
    def removed(self) -> bool:
        return self.emoji is None


@dataclass(frozen=True)
class InboundInteractive:
    """Respuesta del usuario a un mensaje interactivo.

    Cubre los tres tipos que devuelve Meta: ``button_reply`` (botón de respuesta rápida),
    ``list_reply`` (opción de un menú) y ``nfm_reply`` (envío de un Flow).

    El ``id`` es lo que importa para decidir: ``title`` es el texto visible y puede
    cambiar sin que cambie la lógica.
    """

    type: str
    id: str | None = None
    title: str | None = None
    #: Solo en ``list_reply``.
    description: str | None = None
    #: Solo en ``nfm_reply``: el token con el que se lanzó el Flow.
    flow_token: str | None = None
    #: Solo en ``nfm_reply``: ``response_json`` ya parseado.
    flow_response: dict[str, Any] | None = None


@dataclass(frozen=True)
class WebhookInboundMessage:
    phone_number_id: str
    from_user: str
    message_id: str | None
    type: str
    text: str
    raw: dict[str, Any]
    contacts: list[dict[str, Any]] = field(default_factory=list)
    waba_id: str | None = None
    timestamp: str | None = None
    media: InboundMedia | None = None
    #: ``wamid`` del mensaje al que este responde, si es una respuesta citada.
    replied_to: str | None = None
    #: Coordenadas, si el mensaje es de tipo ``location``.
    location: InboundLocation | None = None
    #: Reacción, si el mensaje es de tipo ``reaction``.
    reaction: InboundReaction | None = None
    #: Respuesta a un interactivo (botón, lista o Flow).
    interactive: InboundInteractive | None = None
    #: Tarjetas de contacto que envió el usuario (mensajes de tipo ``contacts``).
    #: Distinto de ``contacts``, que es el perfil de **quien escribe**.
    shared_contacts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def media_id(self) -> str | None:
        """Atajo de compatibilidad: el ``media_id`` del medio, si lo hay."""
        return self.media.media_id if self.media else None

    @property
    def mime_type(self) -> str | None:
        return self.media.mime_type if self.media else None

    @property
    def filename(self) -> str | None:
        return self.media.filename if self.media else None


@dataclass(frozen=True)
class WebhookStatus:
    phone_number_id: str | None
    message_id: str
    status: str
    raw: dict[str, Any]
    recipient_id: str | None = None
    failure_reason: str | None = None
    #: Código de error de Meta cuando ``status`` es ``failed``.
    error_code: int | None = None
    #: ``pricing.category``: ``marketing``, ``marketing_lite``, ``utility``…
    pricing_category: str | None = None
    #: Dato opaco que el host adjuntó al enviar, para correlacionar.
    callback_data: str | None = None


@dataclass(frozen=True)
class WebhookEvents:
    messages: list[WebhookInboundMessage] = field(default_factory=list)
    statuses: list[WebhookStatus] = field(default_factory=list)
