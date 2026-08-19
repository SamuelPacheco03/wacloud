"""Tests del módulo webhook: verificación de firma + parser del payload Meta."""

import hashlib
import hmac

from wacloud.webhook import (
    first_phone_number_id,
    parse_webhook,
    verify_signature,
)
from wacloud.webhook.verify import compute_signature, verify_subscription

# --- verify -----------------------------------------------------------------


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_valid_signature():
    body = b'{"hello":"world"}'
    header = _sign("s3cret", body)
    assert verify_signature(app_secret="s3cret", raw_body=body, signature_header=header)


def test_verify_rejects_wrong_secret():
    body = b'{"hello":"world"}'
    header = _sign("otra", body)
    assert not verify_signature(app_secret="s3cret", raw_body=body, signature_header=header)


def test_verify_handles_missing_or_malformed():
    assert not verify_signature(app_secret="s", raw_body=b"x", signature_header=None)
    assert not verify_signature(app_secret="s", raw_body=b"x", signature_header="md5=abc")
    assert not verify_signature(app_secret="", raw_body=b"x", signature_header="sha256=abc")


def test_compute_signature_roundtrip():
    body = b"payload"
    assert compute_signature("k", body) == _sign("k", body)


# --- parser -----------------------------------------------------------------


def _text_payload():
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA123",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "PNID1"},
                            "contacts": [
                                {"profile": {"name": "Ana"}, "wa_id": "573001112233"}
                            ],
                            "messages": [
                                {
                                    "from": "573001112233",
                                    "id": "wamid.AAA",
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": "hola"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def test_parse_text_message():
    events = parse_webhook(_text_payload())
    assert len(events.messages) == 1
    msg = events.messages[0]
    assert msg.phone_number_id == "PNID1"
    assert msg.waba_id == "WABA123"
    assert msg.from_user == "573001112233"
    assert msg.text == "hola"
    assert msg.media_id is None


def test_parse_media_message_exposes_media_id():
    payload = _text_payload()
    payload["entry"][0]["changes"][0]["value"]["messages"] = [
        {
            "from": "573001112233",
            "id": "wamid.IMG",
            "type": "image",
            "image": {"id": "MID-1", "mime_type": "image/jpeg", "caption": "mira"},
        }
    ]
    events = parse_webhook(payload)
    msg = events.messages[0]
    assert msg.type == "image"
    assert msg.media_id == "MID-1"
    assert msg.mime_type == "image/jpeg"
    assert msg.text == "mira"


def test_parse_interactive_button_reply():
    payload = _text_payload()
    payload["entry"][0]["changes"][0]["value"]["messages"] = [
        {
            "from": "573001112233",
            "id": "wamid.INT",
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": "yes", "title": "Sí"},
            },
        }
    ]
    events = parse_webhook(payload)
    assert events.messages[0].text == "Sí"


def test_parse_statuses():
    payload = {
        "entry": [
            {
                "id": "WABA123",
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "PNID1"},
                            "statuses": [
                                {
                                    "id": "wamid.S",
                                    "status": "DELIVERED",
                                    "recipient_id": "573001112233",
                                }
                            ],
                        }
                    }
                ],
            }
        ]
    }
    events = parse_webhook(payload)
    assert len(events.statuses) == 1
    st = events.statuses[0]
    assert st.message_id == "wamid.S"
    assert st.status == "delivered"
    assert st.recipient_id == "573001112233"


def test_first_phone_number_id():
    assert first_phone_number_id(_text_payload()) == "PNID1"
    assert first_phone_number_id({"entry": []}) is None


# --- Alta de la suscripción (GET hub.challenge) ------------------------------


def test_verify_subscription_returns_challenge():
    assert (
        verify_subscription(
            expected_token="secreto",
            mode="subscribe",
            token="secreto",
            challenge="1158201444",
        )
        == "1158201444"
    )


def test_verify_subscription_rejects_wrong_token():
    assert (
        verify_subscription(
            expected_token="secreto",
            mode="subscribe",
            token="otro",
            challenge="1158201444",
        )
        is None
    )


def test_verify_subscription_rejects_wrong_mode():
    assert (
        verify_subscription(
            expected_token="secreto",
            mode="unsubscribe",
            token="secreto",
            challenge="1158201444",
        )
        is None
    )


def test_verify_subscription_rejects_missing_values():
    for kwargs in (
        {"mode": None, "token": "secreto", "challenge": "1"},
        {"mode": "subscribe", "token": None, "challenge": "1"},
        {"mode": "subscribe", "token": "secreto", "challenge": None},
    ):
        assert verify_subscription(expected_token="secreto", **kwargs) is None


def test_verify_subscription_keeps_challenge_opaque():
    """Meta espera el mismo valor de vuelta: no convertir a int ni reformatear."""
    assert (
        verify_subscription(expected_token="s", mode="subscribe", token="s", challenge="007")
        == "007"
    )


# --- Parseo de ubicación, contactos y reacciones -----------------------------


def _inbound(message):
    """Envuelve un mensaje en la estructura de webhook de Meta."""
    return {
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "PNID"},
                            "messages": [message],
                        }
                    }
                ],
            }
        ]
    }


def test_parse_location_message():
    events = parse_webhook(
        _inbound(
            {
                "from": "573001112233",
                "id": "wamid.L",
                "type": "location",
                "location": {
                    "latitude": 4.711,
                    "longitude": -74.0721,
                    "name": "Plaza Bolívar",
                    "address": "Cra 7, Bogotá",
                },
            }
        )
    )
    message = events.messages[0]
    assert message.location.latitude == 4.711
    assert message.location.name == "Plaza Bolívar"
    assert message.text == "Plaza Bolívar"


def test_location_falls_back_to_coordinates_as_text():
    events = parse_webhook(
        _inbound(
            {
                "from": "573001112233",
                "type": "location",
                "location": {"latitude": 4.711, "longitude": -74.0721},
            }
        )
    )
    assert events.messages[0].text == "4.711, -74.0721"


def test_location_coordinates_arrive_as_numbers():
    """En el webhook Meta manda números, no cadenas como en el envío."""
    events = parse_webhook(
        _inbound(
            {
                "from": "573001112233",
                "type": "location",
                "location": {"latitude": "4.711", "longitude": "-74.07"},
            }
        )
    )
    assert isinstance(events.messages[0].location.latitude, float)


def test_parse_reaction_message():
    events = parse_webhook(
        _inbound(
            {
                "from": "573001112233",
                "id": "wamid.R",
                "type": "reaction",
                "reaction": {"message_id": "wamid.ORIGINAL", "emoji": "👍"},
            }
        )
    )
    reaction = events.messages[0].reaction
    assert reaction.message_id == "wamid.ORIGINAL"
    assert reaction.emoji == "👍"
    assert reaction.removed is False


def test_removed_reaction_has_no_emoji():
    """Meta omite ``emoji`` por completo cuando el usuario retira la reacción."""
    events = parse_webhook(
        _inbound(
            {
                "from": "573001112233",
                "type": "reaction",
                "reaction": {"message_id": "wamid.ORIGINAL"},
            }
        )
    )
    reaction = events.messages[0].reaction
    assert reaction.removed is True
    assert events.messages[0].text == "[reacción retirada]"


def test_parse_shared_contacts():
    events = parse_webhook(
        _inbound(
            {
                "from": "573001112233",
                "type": "contacts",
                "contacts": [
                    {"name": {"formatted_name": "Ana Ruiz"}},
                    {"name": {"formatted_name": "Luis Paz"}},
                ],
            }
        )
    )
    message = events.messages[0]
    assert len(message.shared_contacts) == 2
    assert message.text == "Ana Ruiz, Luis Paz"


def test_shared_contacts_do_not_collide_with_sender_profile():
    """``contacts`` es el perfil de quien escribe; ``shared_contacts``, lo que envía."""
    payload = {
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "PNID"},
                            "contacts": [{"profile": {"name": "Quien escribe"}}],
                            "messages": [
                                {
                                    "from": "573001112233",
                                    "type": "contacts",
                                    "contacts": [
                                        {"name": {"formatted_name": "Tarjeta enviada"}}
                                    ],
                                }
                            ],
                        }
                    }
                ],
            }
        ]
    }
    message = parse_webhook(payload).messages[0]
    assert message.contacts[0]["profile"]["name"] == "Quien escribe"
    assert message.shared_contacts[0]["name"]["formatted_name"] == "Tarjeta enviada"


def test_non_location_message_has_no_location():
    events = parse_webhook(
        _inbound({"from": "573001112233", "type": "text", "text": {"body": "hola"}})
    )
    message = events.messages[0]
    assert message.location is None
    assert message.reaction is None
    assert message.shared_contacts == []


def test_reply_context_is_extracted():
    events = parse_webhook(
        _inbound(
            {
                "from": "573001112233",
                "type": "text",
                "text": {"body": "sí"},
                "context": {"from": "PNID", "id": "wamid.CITADO"},
            }
        )
    )
    assert events.messages[0].replied_to == "wamid.CITADO"


def test_forwarded_context_has_no_replied_to():
    """El ``context`` de reenvío no lleva ``id``: no es una respuesta."""
    events = parse_webhook(
        _inbound(
            {
                "from": "573001112233",
                "type": "text",
                "text": {"body": "mira"},
                "context": {"forwarded": True},
            }
        )
    )
    assert events.messages[0].replied_to is None
