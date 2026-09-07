"""Normalización del destinatario, compartida por todos los builders.

Vive en la raíz del paquete y no dentro de ``messages/`` porque lo usan tanto los
builders de mensajes como los de plantillas. Antes ``templates/builders.py`` importaba
``_recipient`` de ``messages/builders.py``: un módulo dependiendo del privado de otro.

Hay **dos** formas de identificar a un destinatario y no son intercambiables:

- El **teléfono**, en formato E.164 **sin** el ``+`` y sin separadores. Va en ``to``.
- El **BSUID** (*business-scoped user ID*), la identidad que Meta asigna a cada pareja
  usuario y negocio: ``CO.2452497711827233``. Va en ``recipient``, no en ``to``.

El BSUID importa desde que WhatsApp permite nombres de usuario: si el usuario tiene
username y no ha escrito a este número en 30 días, Meta **deja de mandar el teléfono**
en el webhook y el BSUID es lo único con lo que se le puede responder.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/business-scoped-user-ids
"""

from __future__ import annotations

import re
from typing import Any

#: Longitud mínima plausible de un número internacional (código de país + abonado).
_MIN_DIGITS = 5
#: Máximo que permite E.164.
_MAX_DIGITS = 15

#: Forma del BSUID: código de país ISO 3166 alpha-2, un punto y hasta 128 alfanuméricos.
#: Meta avisa de que hay que usarlo entero —quitar el país o el punto hace fallar la
#: petición—, así que aquí solo se reconoce y se pasa tal cual: no se normaliza nada.
_USER_ID_RE = re.compile(r"^[A-Za-z]{2}\.[A-Za-z0-9]{1,128}$")


def digits_only(value: str) -> str:
    """Deja solo los dígitos: ``+57 322 543-21`` -> ``5732254321``."""
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def is_user_id(value: str | None) -> bool:
    """¿Es esto un BSUID y no un teléfono?

    La distinción se puede hacer mirando la cadena porque las dos formas son
    disjuntas: un teléfono no lleva letras ni punto. Eso permite que ``recipient_block``
    acepte cualquiera de las dos sin un argumento extra que habría que propagar por las
    catorce firmas de los builders.
    """
    return bool(value) and bool(_USER_ID_RE.match(str(value).strip()))


def normalize_recipient(to: str) -> str:
    """Normaliza y valida un número de destino.

    Falla aquí en vez de dejar que Meta responda un error críptico: un ``to`` vacío
    produce un ``400`` genérico que no dice cuál de los mensajes del lote iba mal.

    Solo acepta teléfonos. Para un BSUID está ``recipient_block``, que lo manda por el
    campo que le corresponde; pasarlo por aquí lo destrozaría, porque ``CO.24524977…``
    se quedaría en sus dígitos y dejaría de identificar a nadie.
    """
    if is_user_id(to):
        raise ValueError(
            f"destinatario inválido: {to!r} es un BSUID, no un teléfono; "
            "usa recipient_block(), que lo envía como 'recipient'"
        )
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
    """Bloque de cabecera común a todo mensaje individual saliente.

    Acepta un teléfono o un BSUID y elige el campo correspondiente: Meta los pone en
    claves distintas —``to`` y ``recipient``— y mandar un BSUID por ``to`` no falla con
    un error claro, falla con un ``131009`` de parámetro inválido.
    """
    if is_user_id(to):
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "recipient": to.strip(),
        }
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalize_recipient(to),
    }
