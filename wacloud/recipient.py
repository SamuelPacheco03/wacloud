"""Normalización del destinatario, compartida por todos los builders.

Vive en la raíz del paquete y no dentro de ``messages/`` porque lo usan tanto los
builders de mensajes como los de plantillas. Antes ``templates/builders.py`` importaba
``_recipient`` de ``messages/builders.py``: un módulo dependiendo del privado de otro.

La API de Meta espera el número en formato E.164 **sin** el ``+`` y sin separadores.
"""

from __future__ import annotations

from typing import Any

#: Longitud mínima plausible de un número internacional (código de país + abonado).
_MIN_DIGITS = 5
#: Máximo que permite E.164.
_MAX_DIGITS = 15


def digits_only(value: str) -> str:
    """Deja solo los dígitos: ``+57 322 543-21`` -> ``5732254321``."""
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def normalize_recipient(to: str) -> str:
    """Normaliza y valida un número de destino.

    Falla aquí en vez de dejar que Meta responda un error críptico: un ``to`` vacío
    produce un ``400`` genérico que no dice cuál de los mensajes del lote iba mal.
    """
    digits = digits_only(to)
    if not digits:
        raise ValueError(f"destinatario inválido: {to!r} no contiene dígitos")
    if len(digits) < _MIN_DIGITS:
        raise ValueError(
            f"destinatario inválido: {to!r} tiene {len(digits)} dígitos, "
            f"el mínimo es {_MIN_DIGITS}"
        )
    if len(digits) > _MAX_DIGITS:
        raise ValueError(
            f"destinatario inválido: {to!r} tiene {len(digits)} dígitos, "
            f"E.164 permite como máximo {_MAX_DIGITS}"
        )
    return digits


def recipient_block(to: str) -> dict[str, Any]:
    """Bloque de cabecera común a todo mensaje individual saliente."""
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalize_recipient(to),
    }
