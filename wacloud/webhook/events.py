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
    #: Solo en stickers: si el WebP está animado. Meta lo manda únicamente para ellos, así
    #: que en el resto de medios es ``None`` —que aquí significa "no aplica", no "estático"—.
    #: Importa al pintarlo: un sticker animado y uno estático no se muestran igual.
    animated: bool | None = None


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
    #: Identificador con el que **responder**: el teléfono si Meta lo mandó y, si no,
    #: el BSUID. Nunca viene vacío, y ``recipient_block`` acepta cualquiera de los dos,
    #: así que ``send_text(msg.from_user, ...)`` sigue funcionando en ambos casos.
    #:
    #: Ojo al guardarlo: **no siempre es un teléfono**. Para la columna del teléfono
    #: está ``from_phone``, que es ``None`` cuando Meta no lo manda; meter aquí un
    #: ``digits_only`` convertiría ``CO.2452497711827233`` en un número inventado.
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
    #: BSUID de quien escribe (``messages[].from_user_id``). Meta lo manda **siempre**,
    #: tenga el usuario nombre de usuario o no, así que es el identificador estable.
    from_user_id: str | None = None
    #: Teléfono de quien escribe (``messages[].from``), **solo si Meta lo mandó**.
    #: Desaparece cuando el usuario tiene username y además no ha escrito a este número
    #: en 30 días, no está en su agenda, o el negocio le escribió al BSUID.
    from_phone: str | None = None
    #: ``contacts[].profile.username``, si el usuario tiene nombre de usuario.
    username: str | None = None

    @property
    def has_phone_number(self) -> bool:
        """¿Se conoce el teléfono, o solo la identidad de negocio?

        Un hilo sin teléfono se puede seguir respondiendo por la Cloud API, pero no se
        puede cruzar con un CRM que indexe por número.
        """
        return self.from_phone is not None

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
    #: BSUID del destinatario (``statuses[].recipient_user_id``). Meta lo pone siempre,
    #: se haya enviado el mensaje al teléfono o al BSUID; ``recipient_id`` en cambio
    #: puede faltar, por las mismas razones que ``from`` en un mensaje entrante.
    recipient_user_id: str | None = None


@dataclass(frozen=True)
class WebhookTemplateStatus:
    """Cambio de estado de una plantilla, tal como lo notifica Meta.

    Es el **único** aviso de que una plantilla pasó de ``PENDING`` a ``APPROVED`` o
    ``REJECTED``: el nodo de la Graph API dice el estado actual, pero no avisa cuando
    cambia, y la revisión tarda de minutos a días. Sin este evento el host no tiene
    más remedio que sondear.

    ``event`` es el estado nuevo (``APPROVED``, ``REJECTED``, ``PAUSED``, ``DISABLED``,
    ``PENDING_DELETION``, ``ARCHIVED``…). Se guarda como ``str`` y no como ``Enum`` por
    la misma razón que el resto de enumerados que llegan de Meta: la lista crece entre
    versiones y un valor nuevo no puede tumbar el lote.
    """

    waba_id: str | None
    template_id: str | None
    template_name: str | None
    template_language: str | None
    event: str
    raw: dict[str, Any]
    #: Motivo del rechazo o de la pausa. Meta manda la cadena ``"NONE"`` cuando no hay
    #: ninguno; aquí es ``None``, para que el host no tenga que conocer ese valor
    #: mágico ni escribir ``if reason and reason != "NONE"`` en cada sitio.
    reason: str | None = None


@dataclass(frozen=True)
class WebhookDiscarded:
    """Elemento del payload que el parser no supo convertir en un evento.

    Existe porque «lote vacío» y «lote perdido» se veían **exactamente igual** desde
    fuera: el parser descartaba en silencio y no quedaba ni una línea de rastro. Un
    descarte no es un error —Meta manda cosas que aún no interpretamos, y tumbar el lote
    entero sería peor— pero tiene que ser contable.

    ``kind`` es qué se descartó (``message``, ``status``, ``template_status``,
    ``change``) y ``reason`` por qué, con un código estable para poder alertar sin
    parsear prosa. ``raw`` es el fragmento tal cual, para poder reprocesarlo.
    """

    kind: str
    reason: str
    raw: dict[str, Any]
    phone_number_id: str | None = None
    waba_id: str | None = None


@dataclass(frozen=True)
class WebhookEvents:
    messages: list[WebhookInboundMessage] = field(default_factory=list)
    statuses: list[WebhookStatus] = field(default_factory=list)
    #: Cambios de estado de plantillas (``message_template_status_update``). Llegan por
    #: la misma suscripción que los mensajes, pero no tienen nada que ver con ninguna
    #: conversación: son la respuesta de la revisión de Meta.
    template_statuses: list[WebhookTemplateStatus] = field(default_factory=list)
    #: Lo que llegó y no se pudo normalizar. Vacío en el caso normal. Revisarlo —o al
    #: menos contarlo— es la única forma de enterarse de que algo se está perdiendo.
    discarded: list[WebhookDiscarded] = field(default_factory=list)
