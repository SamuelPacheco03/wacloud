"""Constructores de payloads para la Graph API de Meta (``/{pnid}/messages``).

Funciones puras: reciben datos simples y devuelven el ``dict`` listo para POST.
No hacen red ni resuelven credenciales. Cada builder normaliza el destinatario a
solo dígitos y valida lo mínimo imprescindible (p. ej. exigir ``link`` o
``media_id`` en medios).

Mejoras sobre la implementación previa en api-wpp:
- un único helper de destinatario (``_recipient``) en vez de repetir el bloque;
- soporte de ``video`` y ``audio`` (api-wpp no los tenía);
- medios unificados con un helper interno (``_media_object``) en vez de tres
  funciones casi idénticas;
- límites de caption aplicados de forma consistente.
"""
from __future__ import annotations

from typing import Any

#: Tope de caracteres de un caption según la Graph API.
_CAPTION_MAX = 1024


def digits_only(value: str) -> str:
    """Normaliza un número a solo dígitos (``+57 322 543`` -> ``57322543``)."""
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _recipient(to: str) -> dict[str, Any]:
    """Bloque base común a todo mensaje individual."""
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": digits_only(to),
    }


def _media_object(
    *,
    link: str | None,
    media_id: str | None,
    caption: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    """Construye el sub-objeto de un medio (image/document/video/audio).

    Prioriza ``media_id`` (medio ya subido a Meta) sobre ``link`` (URL pública).
    """
    obj: dict[str, Any] = {}
    if media_id and str(media_id).strip():
        obj["id"] = str(media_id).strip()
    elif link and str(link).strip():
        obj["link"] = str(link).strip()
    else:
        raise ValueError("se requiere 'link' o 'media_id'")
    if caption is not None and caption.strip():
        obj["caption"] = caption.strip()[:_CAPTION_MAX]
    if filename is not None and str(filename).strip():
        obj["filename"] = str(filename).strip()
    return obj


def build_text(to: str, body: str, *, preview_url: bool = False) -> dict[str, Any]:
    """Mensaje de texto plano."""
    return {
        **_recipient(to),
        "type": "text",
        "text": {"preview_url": preview_url, "body": body},
    }


def build_image(
    to: str,
    *,
    link: str | None = None,
    media_id: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    """Imagen por URL pública (``link``) o por ``media_id`` ya subido a Meta."""
    return {
        **_recipient(to),
        "type": "image",
        "image": _media_object(link=link, media_id=media_id, caption=caption),
    }


def build_document(
    to: str,
    *,
    link: str | None = None,
    media_id: str | None = None,
    caption: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    """Documento (PDF, Office, etc.) por URL pública o ``media_id``."""
    return {
        **_recipient(to),
        "type": "document",
        "document": _media_object(
            link=link, media_id=media_id, caption=caption, filename=filename
        ),
    }


def build_video(
    to: str,
    *,
    link: str | None = None,
    media_id: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    """Video por URL pública o ``media_id`` (no existía en api-wpp)."""
    return {
        **_recipient(to),
        "type": "video",
        "video": _media_object(link=link, media_id=media_id, caption=caption),
    }


def build_audio(
    to: str,
    *,
    link: str | None = None,
    media_id: str | None = None,
) -> dict[str, Any]:
    """Audio por URL pública o ``media_id`` (audio no admite caption)."""
    return {
        **_recipient(to),
        "type": "audio",
        "audio": _media_object(link=link, media_id=media_id),
    }


def build_interactive_buttons(
    to: str,
    body: str,
    buttons: list[dict[str, str]],
    *,
    header: dict[str, Any] | None = None,
    footer: str | None = None,
) -> dict[str, Any]:
    """Mensaje interactivo con botones de respuesta rápida (máx. 3).

    ``buttons``: lista de ``{"id": ..., "title": ...}``. El título se recorta a
    20 caracteres (límite de Meta).
    """
    action_buttons = [
        {"type": "reply", "reply": {"id": b["id"], "title": str(b["title"])[:20]}}
        for b in buttons[:3]
    ]
    interactive: dict[str, Any] = {
        "type": "button",
        "body": {"text": body},
        "action": {"buttons": action_buttons},
    }
    if header:
        interactive["header"] = header
    if footer:
        interactive["footer"] = {"text": footer}
    return {**_recipient(to), "type": "interactive", "interactive": interactive}


def build_interactive_cta_url(
    to: str,
    body: str,
    button_label: str,
    button_url: str,
    *,
    header: dict[str, Any] | None = None,
    footer: str | None = None,
) -> dict[str, Any]:
    """Mensaje interactivo con un botón CTA que abre una URL."""
    interactive: dict[str, Any] = {
        "type": "cta_url",
        "body": {"text": body},
        "action": {
            "name": "cta_url",
            "parameters": {"display_text": button_label, "url": button_url},
        },
    }
    if header:
        interactive["header"] = header
    if footer:
        interactive["footer"] = {"text": footer}
    return {**_recipient(to), "type": "interactive", "interactive": interactive}


def build_template(
    to: str,
    name: str,
    language_code: str,
    components: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Plantilla genérica (``type=template``). Los componentes van en formato Meta."""
    return {
        **_recipient(to),
        "type": "template",
        "template": {
            "name": str(name).strip(),
            "language": {"code": str(language_code or "es").strip()},
            "components": components or [],
        },
    }


def build_mark_read(
    message_id: str,
    *,
    typing: bool = False,
    typing_type: str = "text",
) -> dict[str, Any]:
    """Payload para marcar un mensaje como leído y, opcionalmente, mostrar el
    indicador de escritura."""
    msg_id = str(message_id).strip()
    if not msg_id:
        raise ValueError("message_id es obligatorio")
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": msg_id,
    }
    if typing:
        payload["typing_indicator"] = {"type": typing_type or "text"}
    return payload
