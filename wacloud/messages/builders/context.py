"""Responder citando un mensaje anterior.

Se implementa como un modificador y no como un parámetro de cada builder: el campo
``context`` funciona igual con **cualquier** tipo de mensaje, así que una sola función
cubre los que hay y los que se añadan después, en vez de repetir el mismo argumento en
diez firmas.
"""

from __future__ import annotations

from typing import Any

__all__ = ["as_reply"]


def as_reply(payload: dict[str, Any], message_id: str) -> dict[str, Any]:
    """Marca un payload como respuesta al mensaje ``message_id``.

    Devuelve una copia: el payload original no se toca, así que se puede reutilizar para
    enviar lo mismo a otro destinatario sin arrastrar la cita.

        >>> as_reply(build_text("573001112233", "Claro"), "wamid.ABC")

    Meta define dos formas de ``context`` mutuamente excluyentes: la de respuesta, con
    ``id``, y la de reenvío, con ``forwarded``. Aquí solo se construye la primera.
    """
    msg_id = str(message_id or "").strip()
    if not msg_id:
        raise ValueError("message_id es obligatorio para responder a un mensaje")
    return {**payload, "context": {"message_id": msg_id}}
