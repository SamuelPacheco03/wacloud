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
    InboundContactCard,
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


def as_id(value: Any) -> str | None:
    """Identificador que Meta manda como número en unos sitios y como cadena en otros.

    El id de plantilla es el caso: llega como ``int`` en el webhook y como ``str`` en
    el nodo de la Graph API. Se normaliza a cadena para que el host no tenga que saber
    por qué puerta entró el dato. ``bool`` se descarta porque en Python es un ``int``,
    y ``True`` no es el identificador de nada.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    return clean_str(value)


# -- Identidad de quien escribe ---------------------------------------------------


def match_contact(
    contacts: list[dict[str, Any]], *, wa_id: str | None, user_id: str | None
) -> dict[str, Any] | None:
    """Perfil de quien escribe, dentro de ``value.contacts``.

    Se empareja en vez de coger el primero porque un lote puede traer mensajes de
    varios remitentes en el mismo ``change``. El BSUID se prueba antes que el teléfono
    porque Meta lo manda siempre, mientras que ``wa_id`` puede faltar.

    Con un solo contacto se devuelve ese aunque no case: Meta ha llegado a mandar el
    perfil sin el identificador con el que emparejarlo, y perder el nombre por eso
    sería peor que asumir lo evidente.
    """
    for contact in contacts:
        if user_id and clean_str(contact.get("user_id")) == user_id:
            return contact
        if wa_id and clean_str(contact.get("wa_id")) == wa_id:
            return contact
    return contacts[0] if len(contacts) == 1 else None


def extract_username(contact: dict[str, Any] | None) -> str | None:
    """``profile.username``: el nombre de usuario de WhatsApp, si el usuario tiene.

    Es lo que hace que el teléfono deje de venir: quien tiene username puede quedar
    identificado solo por su BSUID.
    """
    if contact is None:
        return None
    profile = as_dict(contact.get("profile"))
    return clean_str(profile.get("username")) if profile else None


def contact_card(entry: dict[str, Any]) -> InboundContactCard:
    """Desanida una tarjeta de ``messages[].contacts[]``.

    Meta mete el teléfono dos niveles adentro y en un array —``phones[0].wa_id``—
    aunque el caso normal sea uno solo. Se toma el primero: es el que WhatsApp comparte
    al pulsar el botón, y quedarse con la lista entera devolvería la forma de Meta.
    """
    phones = dict_list(entry.get("phones"))
    first = phones[0] if phones else {}
    name = as_dict(entry.get("name"))
    return InboundContactCard(
        phone=clean_str(first.get("phone")),
        wa_id=clean_str(first.get("wa_id")),
        origin=clean_str(entry.get("origin")),
        name=clean_str(name.get("formatted_name")) if name else None,
        vcard=clean_str(entry.get("vcard")),
    )


def extract_contact_cards(message: dict[str, Any], msg_type: str) -> list[InboundContactCard]:
    if msg_type != "contacts":
        return []
    return [contact_card(entry) for entry in dict_list(message.get("contacts"))]


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
    """Nombres de las tarjetas compartidas; si no los hay, los números.

    La respuesta al botón ``REQUEST_CONTACT_INFO`` **no trae nombre**, solo teléfono, y
    dejarla en ``[contacto recibido]`` escondía justo el dato por el que se pidió.
    """
    labels = []
    for entry in dict_list(message.get("contacts")):
        card = contact_card(entry)
        label = card.name or card.wa_id or card.phone
        if label:
            labels.append(label)
    return ", ".join(labels) if labels else "[contacto recibido]"


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
    animated = typed.get("animated")
    return InboundMedia(
        media_id=clean_str(typed.get("id")),
        mime_type=clean_str(typed.get("mime_type")),
        filename=clean_str(typed.get("filename")),
        sha256=clean_str(typed.get("sha256")),
        # Solo se acepta un booleano de verdad: Meta lo manda así, y colar aquí un
        # `bool(valor)` convertiría cualquier cadena —"false" incluida— en `True`.
        animated=animated if isinstance(animated, bool) else None,
    )


def extract_replied_to(message: dict[str, Any]) -> str | None:
    """``wamid`` citado, si el mensaje responde a otro.

    ``context`` tiene dos formas mutuamente excluyentes: la de respuesta (con ``id``) y
    la de reenvío (con ``forwarded``). Solo la primera trae un mensaje citado.
    """
    context = as_dict(message.get("context"))
    return clean_str(context.get("id")) if context else None
