"""Reacciones a un mensaje recibido."""

from __future__ import annotations

from typing import Any

from wacloud.recipient import recipient_block

__all__ = ["build_reaction", "build_remove_reaction"]


def _reaction(to: str, message_id: str, emoji: str) -> dict[str, Any]:
    msg_id = str(message_id or "").strip()
    if not msg_id:
        raise ValueError("message_id es obligatorio")
    return {
        **recipient_block(to),
        "type": "reaction",
        "reaction": {"message_id": msg_id, "emoji": emoji},
    }


def build_reaction(to: str, message_id: str, emoji: str) -> dict[str, Any]:
    """Reacciona con un emoji a un mensaje concreto.

    ``message_id`` es el ``wamid`` del mensaje al que se reacciona. El emoji puede ir
    como carácter literal o como secuencia unicode escapada.

    Solo se admite **un** emoji: enviar otra reacción al mismo mensaje reemplaza la
    anterior, no la añade.
    """
    clean = str(emoji or "").strip()
    if not clean:
        raise ValueError(
            "el emoji es obligatorio; para retirar una reacción use build_remove_reaction()"
        )
    return _reaction(to, message_id, clean)


def build_remove_reaction(to: str, message_id: str) -> dict[str, Any]:
    """Retira la reacción puesta a un mensaje, enviando un emoji vacío.

    Aviso: la retirada con ``emoji: ""`` **ya no aparece en la documentación actual** de
    Meta. Estuvo en revisiones antiguas y se sigue usando de forma generalizada, pero hoy
    no hay respaldo oficial, así que puede dejar de funcionar sin previo aviso.

    En sentido entrante sí está documentado y es inequívoco: un webhook de reacción
    **sin** el campo ``emoji`` significa que el usuario la retiró.
    """
    return _reaction(to, message_id, "")
