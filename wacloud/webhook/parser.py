"""Parser del payload crudo del webhook de Meta → eventos normalizados.

Convierte la estructura ``entry[].changes[].value`` de la Cloud API en dos listas
tipadas: mensajes entrantes y actualizaciones de estado. Para medios, **no**
resuelve la URL: expone el ``media_id`` (+ mime/filename) para que el host lo
ingiera con su token (ver ``wacloud.media.ingest``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_MEDIA_TYPES = ("image", "audio", "video", "document", "sticker")


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
    media_id: str | None = None
    mime_type: str | None = None
    filename: str | None = None


@dataclass(frozen=True)
class WebhookStatus:
    phone_number_id: str | None
    message_id: str
    status: str
    raw: dict[str, Any]
    recipient_id: str | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class WebhookEvents:
    messages: list[WebhookInboundMessage] = field(default_factory=list)
    statuses: list[WebhookStatus] = field(default_factory=list)


def _clean(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _extract_text_and_media(
    message: dict[str, Any], msg_type: str
) -> tuple[str, str | None, str | None, str | None]:
    """Devuelve (text, media_id, mime_type, filename) según el tipo."""
    typed = message.get(msg_type)

    if msg_type == "text" and isinstance(typed, dict):
        return _clean(typed.get("body")) or "", None, None, None

    if msg_type == "interactive" and isinstance(typed, dict):
        inner = typed.get(typed.get("type", ""), {})
        if isinstance(inner, dict):
            return _clean(inner.get("title")) or _clean(inner.get("id")) or "", None, None, None

    if msg_type == "button" and isinstance(typed, dict):
        return _clean(typed.get("text")) or "", None, None, None

    if msg_type in _MEDIA_TYPES and isinstance(typed, dict):
        text = _clean(typed.get("caption")) or f"[{msg_type} recibido]"
        return (
            text,
            _clean(typed.get("id")),
            _clean(typed.get("mime_type")),
            _clean(typed.get("filename")),
        )

    return f"[{msg_type} recibido]", None, None, None


def _inbound(
    message: dict[str, Any],
    *,
    phone_number_id: str,
    waba_id: str | None,
    contacts: list[dict[str, Any]],
) -> WebhookInboundMessage | None:
    from_user = _clean(message.get("from"))
    if not from_user:
        return None
    msg_type = _clean(message.get("type")) or "unknown"
    text, media_id, mime_type, filename = _extract_text_and_media(message, msg_type)
    return WebhookInboundMessage(
        phone_number_id=phone_number_id,
        from_user=from_user,
        message_id=_clean(message.get("id")),
        type=msg_type,
        text=text,
        raw=message,
        contacts=contacts,
        waba_id=waba_id,
        timestamp=_clean(message.get("timestamp")),
        media_id=media_id,
        mime_type=mime_type,
        filename=filename,
    )


def _status(status: dict[str, Any], *, phone_number_id: str | None) -> WebhookStatus | None:
    message_id = _clean(status.get("id"))
    state = _clean(status.get("status"))
    if not message_id or not state:
        return None
    errors = status.get("errors")
    failure_reason = None
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            failure_reason = _clean(first.get("title")) or _clean(first.get("message")) or str(first)
        else:
            failure_reason = str(first)
    return WebhookStatus(
        phone_number_id=phone_number_id,
        message_id=message_id,
        status=state.lower(),
        raw=status,
        recipient_id=_clean(status.get("recipient_id")),
        failure_reason=failure_reason,
    )


def parse_webhook(payload: dict[str, Any]) -> WebhookEvents:
    """Parsea el payload crudo de Meta en mensajes y estados normalizados."""
    messages: list[WebhookInboundMessage] = []
    statuses: list[WebhookStatus] = []

    entries = payload.get("entry")
    if not isinstance(entries, list):
        return WebhookEvents(messages, statuses)

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        waba_id = _clean(entry.get("id"))
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            value = change.get("value") if isinstance(change, dict) else None
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata")
            phone_number_id = _clean(metadata.get("phone_number_id")) if isinstance(metadata, dict) else None
            contacts = value.get("contacts")
            contacts = [c for c in contacts if isinstance(c, dict)] if isinstance(contacts, list) else []

            if phone_number_id:
                for message in value.get("messages") or []:
                    if isinstance(message, dict):
                        parsed = _inbound(
                            message,
                            phone_number_id=phone_number_id,
                            waba_id=waba_id,
                            contacts=contacts,
                        )
                        if parsed:
                            messages.append(parsed)

            for status in value.get("statuses") or []:
                if isinstance(status, dict):
                    parsed = _status(status, phone_number_id=phone_number_id)
                    if parsed:
                        statuses.append(parsed)

    return WebhookEvents(messages, statuses)


def first_phone_number_id(payload: dict[str, Any]) -> str | None:
    """Atajo para resolver el ``phone_number_id`` antes de verificar la firma."""
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        changes = entry.get("changes") if isinstance(entry, dict) else None
        if not isinstance(changes, list):
            continue
        for change in changes:
            value = change.get("value") if isinstance(change, dict) else None
            metadata = value.get("metadata") if isinstance(value, dict) else None
            pnid = _clean(metadata.get("phone_number_id")) if isinstance(metadata, dict) else None
            if pnid:
                return pnid
    return None
