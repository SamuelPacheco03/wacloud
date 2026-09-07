"""Botón REQUEST_CONTACT_INFO: pedir el teléfono y recibirlo.

Es la vía documentada para conseguir el número de quien llegó identificado solo por su
BSUID. Cierra el círculo que abre ``test_usernames.py``: allí el mensaje entra sin
teléfono, aquí se pide y se une a la identidad.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/business-scoped-user-ids
"""

from __future__ import annotations

import pytest

from tests.factories import accepted_handler, make_messages_client
from wacloud import parse_webhook
from wacloud.messages import builders
from wacloud.templates import ButtonType, buttons, components
from wacloud.webhook import CONTACT_ORIGIN_REQUEST

PNID = "941351305730281"
BSUID = "CO.2452497711827233"


# -- Pedirlo ----------------------------------------------------------------------


def test_interactive_payload_matches_meta():
    """Meta duplica el nombre en ``action.name``, igual que en ``cta_url``."""
    payload = builders.build_request_contact_info(BSUID, "Necesitamos un número 📱")

    assert payload["interactive"] == {
        "type": "request_contact_info",
        "body": {"text": "Necesitamos un número 📱"},
        "action": {"name": "request_contact_info"},
    }


def test_it_can_be_sent_to_someone_we_only_know_by_bsuid():
    """Es el caso entero: a quien tiene teléfono no hace falta pedírselo."""
    assert builders.build_request_contact_info(BSUID, "Hola")["recipient"] == BSUID


def test_header_and_footer_travel_like_in_any_interactive():
    payload = builders.build_request_contact_info(
        BSUID, "Hola", header={"type": "text", "text": "PiddoYa"}, footer="Gracias"
    )

    assert payload["interactive"]["header"] == {"type": "text", "text": "PiddoYa"}
    assert payload["interactive"]["footer"] == {"text": "Gracias"}


def test_a_body_over_the_limit_is_rejected_before_calling_meta():
    with pytest.raises(ValueError, match=r"interactive\.body"):
        builders.build_request_contact_info(BSUID, "x" * 1025)


async def test_the_client_posts_it_to_the_messages_endpoint():
    captured, handler = accepted_handler()

    await make_messages_client(handler).send_request_contact_info(
        BSUID, "Necesitamos tu número", phone_number_id=PNID
    )

    assert captured["path"].endswith(f"/{PNID}/messages")
    assert captured["body"]["interactive"]["type"] == "request_contact_info"


# -- Como botón de plantilla ------------------------------------------------------


def test_the_template_button_is_only_its_type():
    """Meta no deja personalizarlo: sin ``text``, y sin parámetros al enviar."""
    assert buttons.request_contact_info() == {"type": "REQUEST_CONTACT_INFO"}
    assert ButtonType.REQUEST_CONTACT_INFO.value == "REQUEST_CONTACT_INFO"


def test_it_combines_with_other_buttons():
    component = components.buttons(
        [buttons.quick_reply("Ahora no"), buttons.request_contact_info()]
    )

    assert component["buttons"][1] == {"type": "REQUEST_CONTACT_INFO"}


def test_no_quota_is_invented_for_it():
    """Meta no publica un tope. Inventarlo rechazaría plantillas que Meta acepta."""
    component = components.buttons([buttons.request_contact_info()] * 3)

    assert len(component["buttons"]) == 3


# -- Recibirlo --------------------------------------------------------------------


def _shared(*cards: dict) -> dict:
    return {
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": PNID},
                            "contacts": [
                                {"user_id": BSUID, "profile": {"username": "AndrCastillo"}}
                            ],
                            "messages": [
                                {
                                    "id": "wamid.X",
                                    "timestamp": "1788793900",
                                    "type": "contacts",
                                    "from_user_id": BSUID,
                                    "contacts": list(cards),
                                }
                            ],
                        },
                    }
                ],
            }
        ]
    }


def _answer() -> dict:
    """Respuesta al botón: sin nombre y sin vcard, que es lo que manda Meta."""
    return {
        "origin": CONTACT_ORIGIN_REQUEST,
        "phones": [{"phone": "573001234567", "wa_id": "573001234567", "type": "MOBILE"}],
    }


def test_the_answer_joins_both_identities():
    message = parse_webhook(_shared(_answer())).messages[0]

    assert message.from_user_id == BSUID
    assert message.requested_phone == "573001234567"
    assert message.username == "AndrCastillo"


def test_the_card_is_unnested_so_the_host_never_sees_metas_shape():
    card = parse_webhook(_shared(_answer())).messages[0].contact_cards[0]

    assert card.wa_id == "573001234567"
    assert card.phone == "573001234567"
    assert card.from_contact_request
    assert card.vcard is None  # Meta lo omite en una respuesta al botón.


def test_a_card_shared_by_hand_is_not_taken_as_the_users_phone():
    """La comprobación que evita el bug caro: puede ser el número de un tercero.

    Meta usa ``origin`` justamente para distinguirlas, y darlas por equivalentes
    asociaría a un cliente el teléfono de otra persona.
    """
    card = {
        "origin": "other",
        "vcard": "BEGIN:VCARD...",
        "name": {"formatted_name": "Taller de Pedro"},
        "phones": [{"phone": "573009999999", "wa_id": "573009999999"}],
    }

    message = parse_webhook(_shared(card)).messages[0]

    assert message.requested_phone is None
    assert not message.contact_cards[0].from_contact_request
    assert message.contact_cards[0].wa_id == "573009999999"


def test_the_answer_wins_over_a_card_shared_in_the_same_message():
    message = parse_webhook(
        _shared({"origin": "other", "phones": [{"wa_id": "573009999999"}]}, _answer())
    ).messages[0]

    assert message.requested_phone == "573001234567"
    assert len(message.contact_cards) == 2


def test_a_card_without_phones_does_not_explode():
    card = parse_webhook(_shared({"origin": "other"})).messages[0].contact_cards[0]

    assert card.phone is None
    assert card.wa_id is None


def test_the_text_shows_the_number_when_there_is_no_name():
    """Dejarlo en ``[contacto recibido]`` escondía el dato por el que se pidió."""
    assert parse_webhook(_shared(_answer())).messages[0].text == "573001234567"


def test_the_text_still_prefers_the_name_when_it_comes():
    card = {"name": {"formatted_name": "Taller de Pedro"}, "phones": [{"wa_id": "57300"}]}

    assert parse_webhook(_shared(card)).messages[0].text == "Taller de Pedro"


def test_shared_contacts_keeps_the_raw_cards():
    """El crudo no se va: el desanidado se añade, no sustituye."""
    message = parse_webhook(_shared(_answer())).messages[0]

    assert message.shared_contacts == [_answer()]
