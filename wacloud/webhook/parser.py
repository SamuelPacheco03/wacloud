"""Recorrido del payload del webhook y construcción de los eventos.

Meta anida los datos en ``entry[].changes[].value``. Aquí se atraviesa esa estructura
una sola vez y se delega en ``extract`` la interpretación de cada campo.

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
)
from wacloud.webhook.extract import (
    extract_location as _location,
)
from wacloud.webhook.extract import (
    extract_reaction as _reaction,
)

# -- Construcción de eventos ------------------------------------------------------


def _build_message(
    message: dict[str, Any],
    *,
    phone_number_id: str,
    waba_id: str | None,
    contacts: list[dict[str, Any]],
) -> WebhookInboundMessage | None:
    from_user = clean_str(message.get("from"))
    if not from_user:
        return None
    msg_type = clean_str(message.get("type")) or "unknown"
    return WebhookInboundMessage(
        phone_number_id=phone_number_id,
        from_user=from_user,
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


def _iter_change_values(
    payload: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], str | None, str | None]]:
    """Recorre ``entry[].changes[]`` devolviendo valor, ``waba_id`` y nombre del campo.

    Aislar el recorrido de la interpretación mantiene ``parse_webhook`` plano: la
    estructura anidada de Meta se atraviesa en un sitio y una sola vez.

    El campo viaja con el valor porque una misma suscripción entrega cosas que no se
    parecen en nada —mensajes de una conversación y el veredicto sobre una plantilla—
    y es el único dato que dice cuál de las dos es.
    """
    for entry in dict_list(payload.get("entry")):
        waba_id = clean_str(entry.get("id"))
        for change in dict_list(entry.get("changes")):
            value = as_dict(change.get("value"))
            if value is not None:
                yield value, waba_id, clean_str(change.get("field"))


def parse_webhook(payload: dict[str, Any]) -> WebhookEvents:
    """Parsea el payload crudo de Meta en mensajes y estados normalizados."""
    messages: list[WebhookInboundMessage] = []
    statuses: list[WebhookStatus] = []
    template_statuses: list[WebhookTemplateStatus] = []

    for value, waba_id, field_name in _iter_change_values(payload):
        if field_name == TEMPLATE_STATUS_FIELD:
            parsed_template = _build_template_status(value, waba_id=waba_id)
            if parsed_template:
                template_statuses.append(parsed_template)
            continue

        metadata = as_dict(value.get("metadata"))
        phone_number_id = clean_str(metadata.get("phone_number_id")) if metadata else None
        contacts = dict_list(value.get("contacts"))

        if phone_number_id:
            for message in dict_list(value.get("messages")):
                parsed = _build_message(
                    message,
                    phone_number_id=phone_number_id,
                    waba_id=waba_id,
                    contacts=contacts,
                )
                if parsed:
                    messages.append(parsed)

        for status in dict_list(value.get("statuses")):
            parsed_status = _build_status(status, phone_number_id=phone_number_id)
            if parsed_status:
                statuses.append(parsed_status)

    return WebhookEvents(messages, statuses, template_statuses)


def first_phone_number_id(payload: dict[str, Any]) -> str | None:
    """Resuelve el ``phone_number_id`` antes de verificar la firma.

    El host lo necesita para saber qué ``app_secret`` usar, y eso ocurre antes de poder
    confiar en el contenido del payload.
    """
    for value, _, _field in _iter_change_values(payload):
        metadata = as_dict(value.get("metadata"))
        pnid = clean_str(metadata.get("phone_number_id")) if metadata else None
        if pnid:
            return pnid
    return None


#: Reexportados para que ``from wacloud.webhook.parser import ...`` siga funcionando.
__all__ = [
    "InboundInteractive",
    "InboundLocation",
    "InboundMedia",
    "InboundReaction",
    "WebhookEvents",
    "WebhookInboundMessage",
    "WebhookStatus",
    "WebhookTemplateStatus",
    "first_phone_number_id",
    "parse_webhook",
]
