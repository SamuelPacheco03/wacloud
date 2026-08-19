"""Tests del módulo messages: builders puros + MessagesClient con MockTransport."""

import httpx
import pytest

from tests.factories import make_messages_client, make_transport
from wacloud.messages import MessagesClient, builders

# --- Builders (puros, sin red) ---------------------------------------------


def test_build_text_normalizes_recipient():
    payload = builders.build_text("+57 322 543-5272", "hola")
    assert payload["to"] == "573225435272"
    assert payload["type"] == "text"
    assert payload["text"] == {"preview_url": False, "body": "hola"}
    assert payload["messaging_product"] == "whatsapp"


def test_build_image_prefers_media_id_over_link():
    payload = builders.build_image(
        "573000000000", link="https://x/y.jpg", media_id="MID", caption="pie"
    )
    assert payload["image"] == {"id": "MID", "caption": "pie"}


def test_build_document_with_link_and_filename():
    payload = builders.build_document(
        "573000000000", link="https://x/doc.pdf", filename="doc.pdf"
    )
    assert payload["type"] == "document"
    assert payload["document"] == {"link": "https://x/doc.pdf", "filename": "doc.pdf"}


def test_build_video_supported():
    payload = builders.build_video("573000000000", link="https://x/v.mp4")
    assert payload["type"] == "video"
    assert payload["video"] == {"link": "https://x/v.mp4"}


def test_build_audio_has_no_caption():
    payload = builders.build_audio("573000000000", media_id="AID")
    assert payload["audio"] == {"id": "AID"}


def test_media_requires_link_or_id():
    with pytest.raises(ValueError):
        builders.build_image("573000000000")


def test_build_interactive_buttons_rejects_more_than_three():
    """Meta acepta 3 botones: truncar en silencio enviaría algo que el host no pidió."""
    buttons = [{"id": f"b{i}", "title": f"t{i}"} for i in range(5)]
    with pytest.raises(ValueError, match="máximo 3"):
        builders.build_interactive_buttons("573000000000", "elige", buttons)


def test_build_interactive_buttons_rejects_long_title():
    buttons = [{"id": "b0", "title": "x" * 30}]
    with pytest.raises(ValueError, match="máximo 20"):
        builders.build_interactive_buttons("573000000000", "elige", buttons)


def test_build_interactive_buttons_rejects_duplicate_titles():
    buttons = [{"id": "a", "title": "Igual"}, {"id": "b", "title": "Igual"}]
    with pytest.raises(ValueError, match="únicos"):
        builders.build_interactive_buttons("573000000000", "elige", buttons)


def test_build_interactive_buttons_accepts_valid_input():
    buttons = [{"id": "si", "title": "Sí"}, {"id": "no", "title": "No"}]
    payload = builders.build_interactive_buttons(
        "573000000000", "elige", buttons, footer="pie"
    )
    action = payload["interactive"]["action"]["buttons"]
    assert [b["reply"]["id"] for b in action] == ["si", "no"]
    assert payload["interactive"]["footer"] == {"text": "pie"}


def test_build_mark_read_with_typing():
    payload = builders.build_mark_read("wamid.1", typing=True)
    assert payload == {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": "wamid.1",
        "typing_indicator": {"type": "text"},
    }


# --- MessagesClient (con MockTransport) ------------------------------------


def _client(handler) -> MessagesClient:
    return make_messages_client(handler)


async def test_send_text_returns_message_id():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json={"messages": [{"id": "wamid.OK"}]})

    client = _client(handler)
    result = await client.send_text("573000000000", "hola", phone_number_id="PNID")
    assert result.message_id == "wamid.OK"
    assert captured["url"].endswith("/PNID/messages")
    assert captured["auth"] == "Bearer tok"


async def test_send_batch_preserves_order_and_records_partial_failure():
    # El 2º mensaje devuelve 400 (no reintentable): debe quedar failed en su
    # posición sin abortar el 3º.
    seq = iter(
        [
            httpx.Response(200, json={"messages": [{"id": "wamid.1"}]}),
            httpx.Response(400, json={"error": {"message": "bad recipient"}}),
            httpx.Response(200, json={"messages": [{"id": "wamid.3"}]}),
        ]
    )

    def handler(request):
        return next(seq)

    client = _client(handler)
    payloads = [
        builders.build_text("573000000000", "uno"),
        builders.build_text("573000000000", "dos"),
        builders.build_text("573000000000", "tres"),
    ]
    results = await client.send_batch(payloads, phone_number_id="PNID")
    assert [r.ok for r in results] == [True, False, True]
    assert results[0].message_id == "wamid.1"
    assert "bad recipient" in (results[1].error or "")
    assert results[2].message_id == "wamid.3"


async def test_send_batch_all_fail_when_credentials_missing():
    class BrokenResolver:
        async def for_phone_number_id(self, phone_number_id):
            from wacloud.errors import WaInvalidRequest

            raise WaInvalidRequest("sin credenciales")

        async def for_waba_id(self, waba_id):  # pragma: no cover
            raise NotImplementedError

    transport = make_transport(lambda r: httpx.Response(200, json={}))
    client = MessagesClient(transport, BrokenResolver())
    payloads = [builders.build_text("573000000000", "uno")]
    results = await client.send_batch(payloads, phone_number_id="PNID")
    assert results[0].ok is False
    assert "sin credenciales" in (results[0].error or "")


async def test_mark_read_posts_status_payload():
    captured = {}

    def handler(request):
        import json

        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"success": True})

    client = _client(handler)
    await client.mark_read(phone_number_id="PNID", message_id="wamid.X")
    assert captured["body"]["status"] == "read"
    assert captured["body"]["typing_indicator"] == {"type": "text"}
