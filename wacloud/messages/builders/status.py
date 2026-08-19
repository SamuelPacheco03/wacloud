"""Confirmaciones de lectura e indicador de escritura."""

from __future__ import annotations

from typing import Any

__all__ = ["build_mark_read"]


def build_mark_read(
    message_id: str,
    *,
    typing: bool = False,
    typing_type: str = "text",
) -> dict[str, Any]:
    """Marca un mensaje como leído y, opcionalmente, muestra que se está escribiendo.

    No lleva destinatario: Meta lo deduce del mensaje original.

    El indicador dura como máximo 25 s o hasta que se envíe un mensaje. Marcar un mensaje
    como leído marca también todos los anteriores de la conversación.
    """
    msg_id = str(message_id or "").strip()
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
