"""Marcar un envío con una referencia propia del host.

Igual que ``context``, se implementa como un modificador y no como un parámetro de cada
builder: el campo funciona con **cualquier** tipo de mensaje, así que una sola función
cubre los que hay y los que se añadan después.
"""

from __future__ import annotations

from typing import Any

from wacloud.limits import TrackingLimits, ensure_max_length

__all__ = ["with_callback_data"]


def with_callback_data(payload: dict[str, Any], callback_data: str) -> dict[str, Any]:
    """Adjunta ``biz_opaque_callback_data`` al payload.

    Meta no lo interpreta: lo devuelve tal cual en el webhook de estado del mensaje. Es
    la forma de correlacionar un estado entrante con la fila que lo originó sin depender
    del ``wamid``, que solo se conoce **después** de que Meta acepte el envío — y por
    tanto no existe todavía si la respuesta se pierde por el camino.

        >>> with_callback_data(build_text("573001112233", "Hola"), "delivery:018f...")

    Devuelve una copia, como ``as_reply``: el payload original se puede reutilizar para
    otro destinatario sin arrastrar la referencia del anterior.
    """
    data = str(callback_data or "").strip()
    if not data:
        raise ValueError("callback_data no puede estar vacío")
    ensure_max_length(data, TrackingLimits.CALLBACK_DATA, field="biz_opaque_callback_data")
    return {**payload, "biz_opaque_callback_data": data}
