"""Mensajes de texto plano."""

from __future__ import annotations

from typing import Any

from wacloud.limits import TextLimits, ensure_max_length
from wacloud.recipient import recipient_block

__all__ = ["build_text"]


def build_text(to: str, body: str, *, preview_url: bool = False) -> dict[str, Any]:
    """Mensaje de texto plano.

    ``preview_url`` pide a WhatsApp que genere la vista previa del primer enlace.
    """
    text = str(body or "")
    if not text.strip():
        raise ValueError("el cuerpo del mensaje de texto no puede estar vacío")
    ensure_max_length(text, TextLimits.BODY, field="text.body")
    return {
        **recipient_block(to),
        "type": "text",
        "text": {"preview_url": preview_url, "body": text},
    }
