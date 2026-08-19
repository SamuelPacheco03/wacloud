"""Extracción de campos del payload crudo de Meta.

Funciones puras que traducen la forma que manda Meta a los objetos de ``events``.

Criterio: **permisivo al parsear**. Meta envía lotes de hasta 1000 actualizaciones y
añade campos entre versiones; un elemento con forma inesperada se descarta en vez de
tumbar el lote entero. Por eso cada acceso comprueba el tipo antes de usarlo.
"""

from __future__ import annotations

import json as jsonlib
from collections.abc import Callable
from typing import Any

from wacloud.webhook.events import (
    MEDIA_TYPES,
    InboundInteractive,
    InboundLocation,
    InboundMedia,
    InboundReaction,
)

# -- Helpers de extracción -------------------------------------------------------


def clean_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def as_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


# -- Extracción del texto según el tipo de mensaje --------------------------------


def text_from_interactive(typed: dict[str, Any]) -> str:
    """Respuesta a un botón o a una lista.

    El objeto anidado se llama como el valor de ``type`` (``button_reply`` o
    ``list_reply``). Se prefiere el título visible sobre el id, que es interno.
    """
    inner = as_dict(typed.get(typed.get("type", "")))
    if inner is None:
        return ""
    return (
        clean_str(inner.get("title"))
        or clean_str(inner.get("body"))
        or clean_str(inner.get("id"))
        or ""
    )


def text_from_location(typed: dict[str, Any]) -> str:
    """Nombre o dirección del sitio; si no vienen, las coordenadas."""
    label = clean_str(typed.get("name")) or clean_str(typed.get("address"))
    if label:
        return label
    latitude = typed.get("latitude")
    longitude = typed.get("longitude")
    if latitude is not None and longitude is not None:
        return f"{latitude}, {longitude}"
    return "[ubicación recibida]"


def text_from_contacts(message: dict[str, Any]) -> str:
    """Nombres de las tarjetas de contacto compartidas."""
    names = []
    for entry in dict_list(message.get("contacts")):
        name = as_dict(entry.get("name"))
        formatted = clean_str(name.get("formatted_name")) if name else None
        if formatted:
            names.append(formatted)
    return ", ".join(names) if names else "[contacto recibido]"


#: Cómo sacar el texto legible de cada tipo de mensaje. Una tabla en vez de una
#: cascada de ``if``: añadir un tipo nuevo es añadir una entrada, no otra rama.
#: Meta omite ``emoji`` por completo cuando el usuario retira una reacción.
TEXT_EXTRACTORS: dict[str, Callable[[dict[str, Any]], str]] = {
    "text": lambda typed: clean_str(typed.get("body")) or "",
    "interactive": text_from_interactive,
    "button": lambda typed: clean_str(typed.get("text")) or "",
    "reaction": lambda typed: clean_str(typed.get("emoji")) or "[reacción retirada]",
    "location": text_from_location,
}


def extract_text(message: dict[str, Any], msg_type: str) -> str:
    """Texto legible del mensaje, sea cual sea su tipo."""
    if msg_type == "contacts":
        # Los contactos cuelgan del mensaje, no de un sub-objeto homónimo, así que no
        # encajan en la tabla de extractores.
        return text_from_contacts(message)

    typed = as_dict(message.get(msg_type))
    fallback = f"[{msg_type} recibido]"
    if typed is None:
        return fallback

    extractor = TEXT_EXTRACTORS.get(msg_type)
    if extractor is not None:
        return extractor(typed)
    if msg_type in MEDIA_TYPES:
        return clean_str(typed.get("caption")) or fallback
    return fallback


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def extract_location(message: dict[str, Any], msg_type: str) -> InboundLocation | None:
    if msg_type != "location":
        return None
    typed = as_dict(message.get("location"))
    if typed is None:
        return None
    return InboundLocation(
        latitude=as_float(typed.get("latitude")),
        longitude=as_float(typed.get("longitude")),
        name=clean_str(typed.get("name")),
        address=clean_str(typed.get("address")),
        url=clean_str(typed.get("url")),
    )


def extract_reaction(message: dict[str, Any], msg_type: str) -> InboundReaction | None:
    if msg_type != "reaction":
        return None
    typed = as_dict(message.get("reaction"))
    if typed is None:
        return None
    target = clean_str(typed.get("message_id"))
    if not target:
        return None
    return InboundReaction(message_id=target, emoji=clean_str(typed.get("emoji")))


def extract_shared_contacts(message: dict[str, Any], msg_type: str) -> list[dict[str, Any]]:
    if msg_type != "contacts":
        return []
    return dict_list(message.get("contacts"))


def _parse_flow_response(inner: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    """Extrae el token y los datos de un ``nfm_reply``.

    ``response_json`` llega como **cadena JSON**, no como objeto: necesita un segundo
    parseo. Meta además avisa de que la respuesta no incluye el ``flow_id``, así que el
    ``flow_token`` es la única forma de saber a qué envío corresponde.
    """
    raw = inner.get("response_json")
    if not isinstance(raw, str):
        return None, None
    try:
        parsed = jsonlib.loads(raw)
    except ValueError:
        return None, None
    if not isinstance(parsed, dict):
        return None, None
    return clean_str(parsed.get("flow_token")), parsed


def extract_interactive(message: dict[str, Any], msg_type: str) -> InboundInteractive | None:
    """Respuesta a un botón, a una lista o a un Flow."""
    if msg_type != "interactive":
        return None
    typed = as_dict(message.get("interactive"))
    if typed is None:
        return None
    kind = clean_str(typed.get("type"))
    if not kind:
        return None
    inner = as_dict(typed.get(kind))
    if inner is None:
        return InboundInteractive(type=kind)

    if kind == "nfm_reply":
        flow_token, flow_response = _parse_flow_response(inner)
        return InboundInteractive(
            type=kind,
            title=clean_str(inner.get("body")),
            flow_token=flow_token,
            flow_response=flow_response,
        )

    return InboundInteractive(
        type=kind,
        id=clean_str(inner.get("id")),
        title=clean_str(inner.get("title")),
        description=clean_str(inner.get("description")),
    )


def extract_media(message: dict[str, Any], msg_type: str) -> InboundMedia | None:
    if msg_type not in MEDIA_TYPES:
        return None
    typed = as_dict(message.get(msg_type))
    if typed is None:
        return None
    return InboundMedia(
        media_id=clean_str(typed.get("id")),
        mime_type=clean_str(typed.get("mime_type")),
        filename=clean_str(typed.get("filename")),
        sha256=clean_str(typed.get("sha256")),
    )


def extract_replied_to(message: dict[str, Any]) -> str | None:
    """``wamid`` citado, si el mensaje responde a otro.

    ``context`` tiene dos formas mutuamente excluyentes: la de respuesta (con ``id``) y
    la de reenvío (con ``forwarded``). Solo la primera trae un mensaje citado.
    """
    context = as_dict(message.get("context"))
    return clean_str(context.get("id")) if context else None
