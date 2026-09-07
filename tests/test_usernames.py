"""Nombres de usuario de WhatsApp y BSUID (*business-scoped user ID*).

Un usuario con nombre de usuario puede llegar **sin teléfono**: Meta omite ``wa_id`` y
``from`` y lo identifica solo por su BSUID (``CO.2452497711827233``). El parser exigía
``from`` y descartaba esos mensajes en silencio; se perdieron conversaciones enteras
durante días sin dejar una línea de log.

Los dos payloads de aquí son reales, del mismo número y con 45 segundos de diferencia:
el primero traía teléfono y el segundo no.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/business-scoped-user-ids
"""

from __future__ import annotations

import pytest

from tests.factories import (
    accepted_handler,
    capturing_handler,
    make_messages_client,
    make_resolver,
    make_transport,
)
from wacloud.numbers import BlockedUsersClient
from wacloud.recipient import is_user_id, normalize_recipient, recipient_block
from wacloud.webhook import DISCARD_NO_SENDER, parse_webhook

WABA = "915581164329541"
PNID = "941351305730281"


def _change(value: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": WABA, "changes": [{"field": "messages", "value": value}]}],
    }


def _with_phone() -> dict:
    """Payload que siempre funcionó: trae teléfono **y** BSUID."""
    return _change(
        {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "573104058544", "phone_number_id": PNID},
            "contacts": [
                {
                    "wa_id": "573178899484",
                    "user_id": "CO.1087330924463622",
                    "profile": {"name": "Andrés Mesa", "username": "andresdm0"},
                }
            ],
            "messages": [
                {
                    "id": "wamid.HBgTQ08uMTA4NzMzMDkyNDQ2MzYyMhUUABIY",
                    "from": "573178899484",
                    "from_user_id": "CO.1087330924463622",
                    "timestamp": "1788793801",
                    "type": "text",
                    "text": {"body": "Hola"},
                }
            ],
        }
    )


def _without_phone() -> dict:
    """El que se perdía: sin ``wa_id`` ni ``from``, solo identidad de negocio."""
    return _change(
        {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "573104058544", "phone_number_id": PNID},
            "contacts": [
                {
                    "user_id": "CO.2452497711827233",
                    "profile": {"name": "Andrés", "username": "AndrCastillo"},
                }
            ],
            "messages": [
                {
                    "id": "wamid.HBgTQ08uMjQ1MjQ5NzcxMTgyNzIzMxUUABIY",
                    "from_user_id": "CO.2452497711827233",
                    "timestamp": "1788793847",
                    "type": "text",
                    "text": {"body": "Hola"},
                }
            ],
        }
    )


# -- Parseo -----------------------------------------------------------------------


def test_message_without_phone_is_no_longer_dropped():
    """El fallo reportado: `from` ausente tiraba el mensaje entero."""
    events = parse_webhook(_without_phone())

    assert len(events.messages) == 1
    assert events.messages[0].text == "Hola"
    assert not events.discarded


def test_identity_travels_in_the_event():
    events = parse_webhook(_without_phone())
    message = events.messages[0]

    assert message.from_user_id == "CO.2452497711827233"
    assert message.username == "AndrCastillo"
    assert message.from_phone is None
    assert not message.has_phone_number


def test_from_user_falls_back_to_the_bsuid():
    """``from_user`` sigue siendo ``str``: lo que cambia es qué identidad lleva.

    Es lo que permite desplegar sin coordinar: ``send_text(msg.from_user, ...)`` ya
    escribía a quien tocaba y sigue haciéndolo, ahora también sin teléfono.
    """
    assert parse_webhook(_without_phone()).messages[0].from_user == "CO.2452497711827233"


def test_the_phone_still_wins_when_meta_sends_it():
    """Con las dos identidades, ``from_user`` sigue siendo el teléfono de siempre."""
    message = parse_webhook(_with_phone()).messages[0]

    assert message.from_user == "573178899484"
    assert message.from_phone == "573178899484"
    assert message.from_user_id == "CO.1087330924463622"
    assert message.username == "andresdm0"
    assert message.has_phone_number


def test_a_message_with_no_identity_at_all_is_reported_not_swallowed():
    payload = _without_phone()
    del payload["entry"][0]["changes"][0]["value"]["messages"][0]["from_user_id"]

    events = parse_webhook(payload)

    assert not events.messages
    assert [(d.kind, d.reason) for d in events.discarded] == [("message", DISCARD_NO_SENDER)]
    assert events.discarded[0].phone_number_id == PNID


def test_username_is_matched_by_identity_not_by_position():
    """Un ``change`` puede traer mensajes de varios remitentes."""
    payload = _without_phone()
    value = payload["entry"][0]["changes"][0]["value"]
    value["contacts"].insert(
        0, {"user_id": "CO.999", "profile": {"name": "Otra", "username": "otra"}}
    )

    assert parse_webhook(payload).messages[0].username == "AndrCastillo"


def test_status_carries_the_recipient_bsuid():
    """``recipient_user_id`` lo manda Meta siempre; ``recipient_id`` puede faltar."""
    payload = _change(
        {
            "metadata": {"phone_number_id": PNID},
            "statuses": [
                {
                    "id": "wamid.OK",
                    "status": "delivered",
                    "recipient_user_id": "CO.2452497711827233",
                    "timestamp": "1788793900",
                }
            ],
        }
    )

    status = parse_webhook(payload).statuses[0]
    assert status.recipient_user_id == "CO.2452497711827233"
    assert status.recipient_id is None


# -- Envío ------------------------------------------------------------------------


def test_a_bsuid_is_sent_as_recipient_not_as_to():
    """Meta usa claves distintas: el teléfono va en ``to`` y el BSUID en ``recipient``."""
    assert recipient_block("CO.2452497711827233") == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "recipient": "CO.2452497711827233",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CO.2452497711827233", True),
        ("US.13491208655302741918", True),
        ("573178899484", False),
        ("+57 317 889 9484", False),
        ("CO.", False),
        ("COL.123", False),
        ("CO_123", False),
        ("", False),
        (None, False),
    ],
)
def test_bsuid_and_phone_are_distinguishable_by_shape(value, expected):
    """Se decide mirando la cadena, sin un argumento extra en catorce builders.

    Las dos formas son disjuntas: un teléfono no lleva letras ni punto.
    """
    assert is_user_id(value) is expected


def test_normalize_recipient_refuses_a_bsuid_instead_of_mutilating_it():
    """``digits_only`` dejaría ``CO.2452497711827233`` en cifras que no son de nadie."""
    with pytest.raises(ValueError, match="BSUID"):
        normalize_recipient("CO.2452497711827233")


async def test_replying_to_a_username_only_thread_reaches_meta():
    captured, handler = capturing_handler({"messages": [{"id": "wamid.OK"}]})
    message = parse_webhook(_without_phone()).messages[0]

    await make_messages_client(handler).send_text(
        message.from_user, "Buenas", phone_number_id=message.phone_number_id
    )

    assert captured["body"]["recipient"] == "CO.2452497711827233"
    assert "to" not in captured["body"]


async def test_the_routing_is_shared_by_every_builder():
    """Va en ``recipient_block``, así que ningún builder tiene que enterarse."""
    captured, handler = accepted_handler()

    await make_messages_client(handler).send_image(
        "CO.2452497711827233", phone_number_id=PNID, media_id="MID"
    )

    assert captured["body"]["recipient"] == "CO.2452497711827233"


# -- Bloqueo ----------------------------------------------------------------------


async def test_block_uses_user_id_for_a_bsuid():
    """La lista de bloqueo tiene su propia clave: ``user_id``, no ``user``."""
    captured, handler = capturing_handler({"block_users": {"added_users": []}})

    client = BlockedUsersClient(make_transport(handler), make_resolver())
    await client.block(PNID, ["CO.2452497711827233", "573178899484"])

    assert captured["body"]["block_users"] == [
        {"user_id": "CO.2452497711827233"},
        {"user": "573178899484"},
    ]
