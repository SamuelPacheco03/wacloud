"""Recorrido del payload del webhook y construcción de los eventos.

Meta anida los datos en ``entry[].changes[].value``. Aquí se atraviesa esa estructura
una sola vez y se delega en ``extract`` la interpretación de cada campo.

Lo que no se puede normalizar **no desaparece**: va a ``WebhookEvents.discarded`` con
el motivo y el fragmento crudo. Descartar sigue siendo lo correcto —Meta manda cosas
que aún no interpretamos y tumbar el lote entero sería peor—, pero un lote vacío y un
lote perdido tienen que distinguirse desde fuera.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from wacloud.webhook.events import (
    InboundInteractive,
    InboundLocation,
    InboundMedia,
    InboundReaction,
    WebhookDiscarded,
    WebhookEvents,
    WebhookInboundMessage,
    WebhookStatus,
    WebhookTemplateStatus,
)
from wacloud.webhook.extract import (
    as_dict,
    as_id,
    clean_str,
    dict_list,
    extract_interactive,
    extract_media,
    extract_replied_to,
    extract_shared_contacts,
    extract_text,
    extract_username,
    match_contact,
)
from wacloud.webhook.extract import (
    extract_location as _location,
)
from wacloud.webhook.extract import (
    extract_reaction as _reaction,
)

# -- Motivos de descarte ----------------------------------------------------------
#
# Códigos estables, no prosa: el host alerta sobre ellos —o los agrupa en una métrica—
# sin tener que reconocer un mensaje de error que podría cambiar de redacción.

#: El ``change`` no traía un objeto ``value``.
DISCARD_MALFORMED_CHANGE = "malformed_change"
#: Sin ``metadata.phone_number_id`` no se sabe qué número recibió el mensaje.
DISCARD_NO_PHONE_NUMBER_ID = "missing_phone_number_id"
#: Ni ``from`` ni ``from_user_id``: no hay a quién atribuir el mensaje ni a quién responder.
DISCARD_NO_SENDER = "missing_sender"
#: Un estado sin ``id`` o sin ``status`` no dice nada de ningún mensaje.
DISCARD_NO_STATUS_FIELDS = "missing_status_fields"
#: Un ``message_template_status_update`` sin ``event``.
DISCARD_NO_TEMPLATE_EVENT = "missing_template_event"


# -- Construcción de eventos ------------------------------------------------------


def _build_message(
    message: dict[str, Any],
    *,
    phone_number_id: str,
    waba_id: str | None,
    contacts: list[dict[str, Any]],
) -> WebhookInboundMessage | None:
    """Traduce un mensaje entrante al evento normalizado.

    Quien escribe puede venir identificado por teléfono (``from``), por BSUID
    (``from_user_id``) o por ambos. Basta con uno: exigir el teléfono descartaba los
    mensajes de usuarios con nombre de usuario, que es justo el caso en el que Meta
    deja de mandarlo.
    """
    from_phone = clean_str(message.get("from"))
    from_user_id = clean_str(message.get("from_user_id"))
    sender = from_phone or from_user_id
    if not sender:
        return None
    msg_type = clean_str(message.get("type")) or "unknown"
    return WebhookInboundMessage(
        phone_number_id=phone_number_id,
        from_user=sender,
        message_id=clean_str(message.get("id")),
        type=msg_type,
        text=extract_text(message, msg_type),
        raw=message,
        contacts=contacts,
        waba_id=waba_id,
        timestamp=clean_str(message.get("timestamp")),
        media=extract_media(message, msg_type),
        replied_to=extract_replied_to(message),
        location=_location(message, msg_type),
        reaction=_reaction(message, msg_type),
        interactive=extract_interactive(message, msg_type),
        shared_contacts=extract_shared_contacts(message, msg_type),
        from_user_id=from_user_id,
        from_phone=from_phone,
        username=extract_username(
            match_contact(contacts, wa_id=from_phone, user_id=from_user_id)
        ),
    )


def _first_error(status: dict[str, Any]) -> tuple[str | None, int | None]:
    """Motivo y código del primer error, cuando el estado es ``failed``."""
    errors = dict_list(status.get("errors"))
    if not errors:
        return None, None
    first = errors[0]
    details = as_dict(first.get("error_data"))
    reason = (
        (clean_str(details.get("details")) if details else None)
        or clean_str(first.get("title"))
        or clean_str(first.get("message"))
    )
    code = first.get("code")
    return reason, code if isinstance(code, int) and not isinstance(code, bool) else None


def _build_status(
    status: dict[str, Any], *, phone_number_id: str | None
) -> WebhookStatus | None:
    message_id = clean_str(status.get("id"))
    state = clean_str(status.get("status"))
    if not message_id or not state:
        return None

    reason, code = _first_error(status)
    pricing = as_dict(status.get("pricing"))
    return WebhookStatus(
        phone_number_id=phone_number_id,
        message_id=message_id,
        status=state.lower(),
        raw=status,
        recipient_id=clean_str(status.get("recipient_id")),
        failure_reason=reason,
        error_code=code,
        pricing_category=clean_str(pricing.get("category")) if pricing else None,
        callback_data=clean_str(status.get("biz_opaque_callback_data")),
        recipient_user_id=clean_str(status.get("recipient_user_id")),
    )


#: Campo de ``changes[]`` que trae el resultado de la revisión de una plantilla.
TEMPLATE_STATUS_FIELD = "message_template_status_update"

#: Meta usa esta cadena para decir "sin motivo", en vez de omitir el campo.
_NO_REASON = "NONE"


def _build_template_status(
    value: dict[str, Any], *, waba_id: str | None
) -> WebhookTemplateStatus | None:
    """Traduce un ``message_template_status_update`` al evento normalizado.

    Sin ``event`` no hay nada que contar, así que se descarta en vez de propagar un
    cambio de estado sin estado. Es también lo que hace inofensivo que Meta mande por
    este mismo campo variantes que aún no interpretamos.
    """
    event = clean_str(value.get("event"))
    if not event:
        return None

    reason = clean_str(value.get("reason"))
    return WebhookTemplateStatus(
        waba_id=waba_id,
        template_id=as_id(value.get("message_template_id")),
        template_name=clean_str(value.get("message_template_name")),
        template_language=clean_str(value.get("message_template_language")),
        event=event,
        raw=value,
        reason=None if reason == _NO_REASON else reason,
    )


# -- Recorrido del payload --------------------------------------------------------


def _iter_changes(payload: dict[str, Any]) -> Iterator[tuple[dict[str, Any], str | None]]:
    """Recorre ``entry[].changes[]`` devolviendo cada cambio y su ``waba_id``.

    Aislar el recorrido de la interpretación mantiene ``parse_webhook`` plano: la
    estructura anidada de Meta se atraviesa en un sitio y una sola vez.

    Devuelve el ``change`` entero y no solo su ``value`` porque quien llama necesita las
    dos cosas: el ``field`` para saber qué llegó —una misma suscripción entrega mensajes
    de una conversación y el veredicto sobre una plantilla— y el cambio crudo para poder
    anotarlo como descarte cuando no trae ``value``.
    """
    for entry in dict_list(payload.get("entry")):
        waba_id = clean_str(entry.get("id"))
        for change in dict_list(entry.get("changes")):
            yield change, waba_id


def _collect_conversation(
    value: dict[str, Any], *, waba_id: str | None, into: WebhookEvents
) -> None:
    """Vuelca los mensajes y estados de un ``change`` de conversación."""
    metadata = as_dict(value.get("metadata"))
    phone_number_id = clean_str(metadata.get("phone_number_id")) if metadata else None
    contacts = dict_list(value.get("contacts"))

    for message in dict_list(value.get("messages")):
        parsed = (
            _build_message(
                message,
                phone_number_id=phone_number_id,
                waba_id=waba_id,
                contacts=contacts,
            )
            if phone_number_id
            else None
        )
        if parsed:
            into.messages.append(parsed)
            continue
        into.discarded.append(
            WebhookDiscarded(
                kind="message",
                reason=DISCARD_NO_SENDER if phone_number_id else DISCARD_NO_PHONE_NUMBER_ID,
                raw=message,
                phone_number_id=phone_number_id,
                waba_id=waba_id,
            )
        )

    for status in dict_list(value.get("statuses")):
        parsed_status = _build_status(status, phone_number_id=phone_number_id)
        if parsed_status:
            into.statuses.append(parsed_status)
            continue
        into.discarded.append(
            WebhookDiscarded(
                kind="status",
                reason=DISCARD_NO_STATUS_FIELDS,
                raw=status,
                phone_number_id=phone_number_id,
                waba_id=waba_id,
            )
        )


def _collect_template_status(
    value: dict[str, Any], *, waba_id: str | None, into: WebhookEvents
) -> None:
    parsed = _build_template_status(value, waba_id=waba_id)
    if parsed:
        into.template_statuses.append(parsed)
        return
    into.discarded.append(
        WebhookDiscarded(
            kind="template_status",
            reason=DISCARD_NO_TEMPLATE_EVENT,
            raw=value,
            waba_id=waba_id,
        )
    )


def parse_webhook(payload: dict[str, Any]) -> WebhookEvents:
    """Parsea el payload crudo de Meta en mensajes y estados normalizados.

    Nada se pierde en silencio: lo que no se pudo normalizar queda en ``discarded``.
    """
    events = WebhookEvents()

    for change, waba_id in _iter_changes(payload):
        value = as_dict(change.get("value"))
        if value is None:
            events.discarded.append(
                WebhookDiscarded(
                    kind="change",
                    reason=DISCARD_MALFORMED_CHANGE,
                    raw=change,
                    waba_id=waba_id,
                )
            )
            continue
        if clean_str(change.get("field")) == TEMPLATE_STATUS_FIELD:
            _collect_template_status(value, waba_id=waba_id, into=events)
        else:
            _collect_conversation(value, waba_id=waba_id, into=events)

    return events


def first_phone_number_id(payload: dict[str, Any]) -> str | None:
    """Resuelve el ``phone_number_id`` antes de verificar la firma.

    El host lo necesita para saber qué ``app_secret`` usar, y eso ocurre antes de poder
    confiar en el contenido del payload.
    """
    for change, _waba_id in _iter_changes(payload):
        value = as_dict(change.get("value"))
        metadata = as_dict(value.get("metadata")) if value else None
        pnid = clean_str(metadata.get("phone_number_id")) if metadata else None
        if pnid:
            return pnid
    return None


#: Reexportados para que ``from wacloud.webhook.parser import ...`` siga funcionando.
__all__ = [
    "DISCARD_MALFORMED_CHANGE",
    "DISCARD_NO_PHONE_NUMBER_ID",
    "DISCARD_NO_SENDER",
    "DISCARD_NO_STATUS_FIELDS",
    "DISCARD_NO_TEMPLATE_EVENT",
    "InboundInteractive",
    "InboundLocation",
    "InboundMedia",
    "InboundReaction",
    "WebhookDiscarded",
    "WebhookEvents",
    "WebhookInboundMessage",
    "WebhookStatus",
    "WebhookTemplateStatus",
    "first_phone_number_id",
    "parse_webhook",
]
