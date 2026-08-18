"""Tests del módulo webhook: verificación de firma + parser del payload Meta."""
import hashlib
import hmac

from wacloud.webhook import (
    first_phone_number_id,
    parse_webhook,
    verify_signature,
)
from wacloud.webhook.verify import compute_signature


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
                            "contacts": [{"profile": {"name": "Ana"}, "wa_id": "573001112233"}],
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
