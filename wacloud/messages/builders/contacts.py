"""Mensajes de contacto (tarjeta de visita).

Es el tipo de mensaje con la estructura más profunda de la Cloud API: un contacto agrupa
nombre, organización, teléfonos, correos, direcciones y URLs, casi todo opcional. Armar
ese diccionario a mano es propenso a error, así que cada parte tiene su constructor y se
componen.

Meta solo exige de verdad ``name.formatted_name``. El resto es opcional, pero dentro de
cada lista hay campos obligatorios: un teléfono necesita ``phone``, un correo ``email`` y
una URL ``url``.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/contacts
"""

from __future__ import annotations

import re
from typing import Any

from wacloud.recipient import recipient_block

__all__ = [
    "build_contacts",
    "contact",
    "contact_address",
    "contact_email",
    "contact_name",
    "contact_org",
    "contact_phone",
    "contact_url",
]

#: Meta espera el cumpleaños en ISO 8601 corto.
_BIRTHDAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _compact(values: dict[str, Any]) -> dict[str, Any]:
    """Quita las claves vacías: Meta rechaza cadenas en blanco en algunos campos."""
    return {k: v for k, v in values.items() if v not in (None, "", [], {})}


def contact_name(
    formatted_name: str,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    middle_name: str | None = None,
    prefix: str | None = None,
    suffix: str | None = None,
) -> dict[str, Any]:
    """Nombre del contacto. ``formatted_name`` es el único campo que Meta exige."""
    clean = str(formatted_name or "").strip()
    if not clean:
        raise ValueError("formatted_name es obligatorio")
    return _compact(
        {
            "formatted_name": clean,
            "first_name": first_name,
            "last_name": last_name,
            "middle_name": middle_name,
            "prefix": prefix,
            "suffix": suffix,
        }
    )


def contact_phone(
    phone: str, *, type: str | None = None, wa_id: str | None = None
) -> dict[str, Any]:
    """Teléfono del contacto.

    ``wa_id`` marca el número como usuario de WhatsApp y hace que la tarjeta ofrezca
    abrir el chat directamente.

    ``type`` es texto libre en los ejemplos de Meta (``"Mobile"``, ``"Work"``), aunque su
    esquema OpenAPI lo declare como enum ``HOME``/``WORK``. Se acepta cualquier cadena:
    restringirlo rechazaría valores que Meta admite.
    """
    clean = str(phone or "").strip()
    if not clean:
        raise ValueError("el número de teléfono es obligatorio")
    return _compact({"phone": clean, "type": type, "wa_id": wa_id})


def contact_email(email: str, *, type: str | None = None) -> dict[str, Any]:
    """Correo electrónico del contacto."""
    clean = str(email or "").strip()
    if not clean:
        raise ValueError("el correo es obligatorio")
    return _compact({"email": clean, "type": type})


def contact_url(url: str, *, type: str | None = None) -> dict[str, Any]:
    """Página web del contacto."""
    clean = str(url or "").strip()
    if not clean:
        raise ValueError("la URL es obligatoria")
    return _compact({"url": clean, "type": type})


def contact_address(
    *,
    street: str | None = None,
    city: str | None = None,
    state: str | None = None,
    zip: str | None = None,
    country: str | None = None,
    country_code: str | None = None,
    type: str | None = None,
) -> dict[str, Any]:
    """Dirección postal del contacto. Todos los campos son opcionales para Meta.

    Se exige al menos uno con contenido: una dirección vacía ocupa sitio en la tarjeta y
    no muestra nada.
    """
    address = _compact(
        {
            "street": street,
            "city": city,
            "state": state,
            "zip": zip,
            "country": country,
            "country_code": country_code,
            "type": type,
        }
    )
    if not address:
        raise ValueError("la dirección necesita al menos un campo con contenido")
    return address


def contact_org(
    *,
    company: str | None = None,
    department: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Datos laborales del contacto."""
    org = _compact({"company": company, "department": department, "title": title})
    if not org:
        raise ValueError("la organización necesita al menos un campo con contenido")
    return org


def contact(
    name: dict[str, Any],
    *,
    phones: list[dict[str, Any]] | None = None,
    emails: list[dict[str, Any]] | None = None,
    urls: list[dict[str, Any]] | None = None,
    addresses: list[dict[str, Any]] | None = None,
    org: dict[str, Any] | None = None,
    birthday: str | None = None,
) -> dict[str, Any]:
    """Une las partes en un contacto completo.

    ``birthday`` va en formato ``YYYY-MM-DD``.
    """
    if not isinstance(name, dict) or not name.get("formatted_name"):
        raise ValueError("se requiere un 'name' construido con contact_name()")

    if birthday is not None and not _BIRTHDAY.match(str(birthday).strip()):
        raise ValueError(f"birthday debe tener el formato YYYY-MM-DD, no {birthday!r}")

    return _compact(
        {
            "name": name,
            "birthday": birthday,
            "org": org,
            "phones": phones,
            "emails": emails,
            "urls": urls,
            "addresses": addresses,
        }
    )


def build_contacts(to: str, contacts: list[dict[str, Any]]) -> dict[str, Any]:
    """Envía una o varias tarjetas de contacto."""
    if not contacts:
        raise ValueError("se requiere al menos un contacto")
    for entry in contacts:
        if not isinstance(entry, dict) or "name" not in entry:
            raise ValueError("cada contacto debe construirse con contact() e incluir 'name'")
    return {
        **recipient_block(to),
        "type": "contacts",
        "contacts": list(contacts),
    }
