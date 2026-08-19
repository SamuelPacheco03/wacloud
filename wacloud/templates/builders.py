"""Builders de envío de plantillas: autenticación (OTP) y marketing.

Separación respecto a ``messages/builders``:

- ``messages.builders.build_template`` arma el envío de **cualquier** plantilla y es la
  base de todo lo de aquí;
- este módulo aporta los **componentes** de los casos que tienen forma fija: el código
  OTP de las plantillas de autenticación y el payload de la Marketing Messages API.

Las tres variantes de autenticación (``copy_code``, ``one_tap``, ``zero_tap``) comparten
el mismo payload de envío: el código va en el cuerpo y, si hay botón, también como
parámetro del botón. Lo que las diferencia es cómo se aprobó la plantilla en Meta, no
cómo se envía.
"""

from __future__ import annotations

from typing import Any

from wacloud.messages.builders import build_template
from wacloud.recipient import digits_only

__all__ = [
    "build_auth_basic",
    "build_auth_code",
    "build_auth_copy_code",
    "build_marketing_template",
]


def _auth_components(code: str, *, with_button: bool) -> list[dict[str, Any]]:
    """Componentes de una plantilla de autenticación.

    El código aparece dos veces cuando hay botón: en el ``BODY`` y en el parámetro del
    botón URL. Meta lo exige así para las plantillas con botón OTP, sea ``copy_code``,
    ``one_tap`` o ``zero_tap``.
    """
    components: list[dict[str, Any]] = [
        {"type": "body", "parameters": [{"type": "text", "text": code}]}
    ]
    if with_button:
        components.append(
            {
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [{"type": "text", "text": code}],
            }
        )
    return components


def build_auth_code(
    to: str,
    name: str,
    code: str,
    *,
    language_code: str = "es",
    with_button: bool = True,
) -> dict[str, Any]:
    """Envía un código OTP con una plantilla de autenticación aprobada.

    ``with_button=True`` cubre las plantillas con botón OTP (copy_code, one_tap y
    zero_tap, que se envían igual). ``with_button=False`` cubre las que solo muestran
    el código en el cuerpo.

    El número de parámetros debe coincidir con el de la plantilla aprobada: si no
    coincide, Meta responde el código ``132000``.
    """
    clean_code = str(code or "").strip()
    if not clean_code:
        raise ValueError("el código de autenticación es obligatorio")
    return build_template(
        to, name, language_code, _auth_components(clean_code, with_button=with_button)
    )


def build_auth_copy_code(
    to: str, name: str, code: str, *, language_code: str = "es"
) -> dict[str, Any]:
    """Plantilla de autenticación con botón (copiar código, one-tap o zero-tap)."""
    return build_auth_code(to, name, code, language_code=language_code, with_button=True)


def build_auth_basic(
    to: str, name: str, code: str, *, language_code: str = "es"
) -> dict[str, Any]:
    """Plantilla de autenticación sin botón: solo muestra el código en el cuerpo."""
    return build_auth_code(to, name, code, language_code=language_code, with_button=False)


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
    """Payload para ``POST /{phone_number_id}/marketing_messages``.

    La Marketing Messages API (antes "MM Lite") es GA desde noviembre de 2025 y solo
    acepta plantillas de categoría ``MARKETING``: enviar una de utilidad o autenticación
    devuelve el código ``134100``.

    Requiere ``to`` y/o ``recipient`` (un BSUID). Si van ambos, Meta prioriza ``to``.

    ``product_policy`` admite ``CLOUD_API_FALLBACK`` (si el mensaje no es elegible para
    MM, se entrega por Cloud API) o ``STRICT`` (falla en vez de caer de vuelta). Meta no
    documenta cuál es el valor por defecto, así que conviene fijarlo explícitamente
    cuando la entrega por MM debe ser determinista.
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
