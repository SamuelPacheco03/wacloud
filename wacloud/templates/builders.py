"""Builders de plantillas: envío de OTP (auth) y de marketing.

Separación clara respecto a ``messages/builders``:
- aquí van los payloads específicos de *plantillas* (componentes con parámetros);
- el envío de una plantilla genérica ya aprobada se hace con
  ``messages.builders.build_template`` (o ``MessagesClient.send_template``).

Las variantes de autenticación (``copy_code``, ``basic``, ``autofill``) cambian
solo en los componentes/botón; el cuerpo siempre lleva el código como parámetro.
"""
from __future__ import annotations

from typing import Any

from wacloud.messages.builders import _recipient, digits_only


def _auth_template_message(
    to: str,
    name: str,
    language_code: str,
    components: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        **_recipient(to),
        "type": "template",
        "template": {
            "name": str(name).strip(),
            "language": {"code": str(language_code or "es").strip()},
            "components": components,
        },
    }


def build_auth_copy_code(
    to: str, name: str, code: str, *, language_code: str = "es"
) -> dict[str, Any]:
    """Plantilla de autenticación con botón "Copiar código".

    El código va dos veces: en el cuerpo (BODY) y en el parámetro del botón URL.
    La plantilla debe estar aprobada en Meta con 1 parámetro de body y 1 de botón.
    """
    code = str(code).strip()
    return _auth_template_message(
        to,
        name,
        language_code,
        [
            {"type": "body", "parameters": [{"type": "text", "text": code}]},
            {
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [{"type": "text", "text": code}],
            },
        ],
    )


def build_auth_basic(
    to: str, name: str, code: str, *, language_code: str = "es"
) -> dict[str, Any]:
    """Plantilla de autenticación básica (solo muestra el código, sin botón)."""
    code = str(code).strip()
    return _auth_template_message(
        to,
        name,
        language_code,
        [{"type": "body", "parameters": [{"type": "text", "text": code}]}],
    )


def build_auth_autofill(
    to: str, name: str, code: str, *, language_code: str = "es"
) -> dict[str, Any]:
    """Plantilla de autenticación con botón de autocompletado (one-tap).

    El botón es ``sub_type="url"`` (one-tap autofill); a efectos de envío el
    parámetro es el mismo código, igual que copy_code. La diferencia real está en
    cómo se aprobó la plantilla en Meta (botón OTP autofill vs copy_code).
    """
    return build_auth_copy_code(to, name, code, language_code=language_code)


def build_marketing_template(
    *,
    name: str,
    language_code: str,
    components: list[dict[str, Any]] | None = None,
    to: str | None = None,
    recipient: str | None = None,
    product_policy: str | None = None,
    message_activity_sharing: bool | None = None,
) -> dict[str, Any]:
    """Payload para ``POST /{pnid}/marketing_messages`` (plantillas de marketing).

    Requiere al menos ``to`` o ``recipient``; si hay ambos, Meta prioriza ``to``.
    """
    to_clean = digits_only(to) if to else ""
    recipient_clean = (recipient or "").strip()
    if not to_clean and not recipient_clean:
        raise ValueError("se requiere 'to' y/o 'recipient'")

    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "type": "template",
        "template": {
            "name": str(name).strip(),
            "language": {"code": str(language_code or "es").strip()},
            "components": components or [],
        },
    }
    if to_clean:
        payload["to"] = to_clean
    if recipient_clean:
        payload["recipient"] = recipient_clean
    if product_policy:
        payload["product_policy"] = product_policy
    if message_activity_sharing is not None:
        payload["message_activity_sharing"] = message_activity_sharing
    return payload
