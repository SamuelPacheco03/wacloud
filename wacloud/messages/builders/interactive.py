"""Mensajes interactivos: botones de respuesta rápida y botón CTA con URL."""

from __future__ import annotations

from typing import Any

from wacloud.limits import InteractiveLimits, ensure_max_items, ensure_max_length
from wacloud.recipient import recipient_block

__all__ = [
    "build_interactive_buttons",
    "build_interactive_cta_url",
    "interactive_message",
]


def interactive_message(
    to: str,
    interactive: dict[str, Any],
    *,
    header: dict[str, Any] | None,
    footer: str | None,
) -> dict[str, Any]:
    """Envuelve un objeto ``interactive`` en el mensaje completo.

    Público porque lo comparten los tres tipos de interactivo (botones, lista y
    Flow), que viven en módulos distintos.
    """
    if header:
        interactive["header"] = header
    if footer:
        interactive["footer"] = {
            "text": ensure_max_length(
                footer, InteractiveLimits.FOOTER, field="interactive.footer"
            )
        }
    return {**recipient_block(to), "type": "interactive", "interactive": interactive}


def build_interactive_buttons(
    to: str,
    body: str,
    buttons: list[dict[str, str]],
    *,
    header: dict[str, Any] | None = None,
    footer: str | None = None,
) -> dict[str, Any]:
    """Mensaje interactivo con botones de respuesta rápida.

    ``buttons``: lista de ``{"id": ..., "title": ...}``, máximo 3. Los títulos deben ser
    únicos: WhatsApp no distingue dos botones con la misma etiqueta y Meta rechaza el
    payload.
    """
    if not buttons:
        raise ValueError("se requiere al menos un botón")
    ensure_max_items(
        list(buttons), InteractiveLimits.MAX_REPLY_BUTTONS, field="action.buttons"
    )
    ensure_max_length(body, InteractiveLimits.BODY, field="interactive.body")

    titles = [str(b["title"]) for b in buttons]
    if len(set(titles)) != len(titles):
        raise ValueError("los títulos de los botones deben ser únicos")

    action_buttons = [
        {
            "type": "reply",
            "reply": {
                "id": ensure_max_length(
                    str(b["id"]), InteractiveLimits.REPLY_BUTTON_ID, field="reply.id"
                ),
                "title": ensure_max_length(
                    str(b["title"]),
                    InteractiveLimits.REPLY_BUTTON_TITLE,
                    field="reply.title",
                ),
            },
        }
        for b in buttons
    ]
    interactive: dict[str, Any] = {
        "type": "button",
        "body": {"text": body},
        "action": {"buttons": action_buttons},
    }
    return interactive_message(to, interactive, header=header, footer=footer)


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
    ensure_max_length(body, InteractiveLimits.BODY, field="interactive.body")
    ensure_max_length(
        button_label, InteractiveLimits.CTA_DISPLAY_TEXT, field="action.display_text"
    )
    if not str(button_url or "").strip():
        raise ValueError("se requiere 'button_url'")

    interactive: dict[str, Any] = {
        "type": "cta_url",
        "body": {"text": body},
        "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": button_label,
                "url": str(button_url).strip(),
            },
        },
    }
    return interactive_message(to, interactive, header=header, footer=footer)
