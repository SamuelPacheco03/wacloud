"""Tests del transporte con httpx.MockTransport (sin red real)."""

import httpx
import pytest

from tests.factories import make_messages_client, make_transport
from wacloud.config import GraphConfig
from wacloud.errors import (
    WaInvalidRequest,
    WaRateLimited,
    WaServerError,
    WaTransportError,
)
from wacloud.transport import Transport


def _transport_with(handler, *, max_retries: int = 0) -> Transport:
    return make_transport(handler, max_retries=max_retries)


async def test_success_returns_json():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    t = _transport_with(handler)
    out = await t.request("POST", "/pnid/messages", access_token="tok", json={"x": 1})
    assert out["messages"][0]["id"] == "wamid.1"


async def test_non_retryable_raises_immediately():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": "bad"}})

    t = _transport_with(handler, max_retries=3)
    with pytest.raises(WaInvalidRequest):
        await t.request("POST", "/pnid/messages", access_token="tok")
    assert calls["n"] == 1  # no se reintenta un 4xx


async def test_retries_on_500_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json={"ok": True})

    t = _transport_with(handler, max_retries=3)
    out = await t.request("POST", "/pnid/messages", access_token="tok")
    assert out["ok"] is True
    assert calls["n"] == 3


async def test_rate_limited_exhausts_and_raises():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "slow down"})

    t = _transport_with(handler, max_retries=2)
    with pytest.raises(WaRateLimited):
        await t.request("POST", "/pnid/messages", access_token="tok")
    assert calls["n"] == 3  # 1 inicial + 2 reintentos


async def test_server_error_exhausts_and_raises():
    def handler(request):
        return httpx.Response(503, json={"error": "unavailable"})

    t = _transport_with(handler, max_retries=1)
    with pytest.raises(WaServerError):
        await t.request("POST", "/pnid/messages", access_token="tok")


async def test_graph_url_built_with_version():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})

    config = GraphConfig(
        base_url="https://graph.facebook.com",
        api_version="v20.0",
    )
    t = make_transport(handler, config=config)
    await t.request("POST", "/123/messages", access_token="tok")
    assert captured["url"] == "https://graph.facebook.com/v20.0/123/messages"


# --- Peticiones no idempotentes ---------------------------------------------
#
# Un envío que se reintenta tras un fallo ambiguo le manda al destinatario el mismo
# mensaje dos veces. La librería no guarda estado, así que la única defensa es no
# reintentar lo que no demuestra que Meta rechazó la petición.


async def test_non_idempotent_does_not_retry_a_transport_error():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectTimeout("timeout")

    t = _transport_with(handler, max_retries=3)
    with pytest.raises(WaTransportError):
        await t.request("POST", "/pnid/messages", access_token="tok", idempotent=False)
    assert calls["n"] == 1


async def test_idempotent_still_retries_a_transport_error():
    """El caso de al lado, sin cambios: repetir una lectura es gratis."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectTimeout("timeout")
        return httpx.Response(200, json={"ok": True})

    t = _transport_with(handler, max_retries=3)
    assert await t.request("GET", "/pnid", access_token="tok") == {"ok": True}
    assert calls["n"] == 3


async def test_non_idempotent_does_not_retry_a_5xx_without_a_known_code():
    """Un 502 pelado no dice si Meta procesó el envío."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(502, json={"error": {"message": "bad gateway"}})

    t = _transport_with(handler, max_retries=3)
    with pytest.raises(WaServerError):
        await t.request("POST", "/pnid/messages", access_token="tok", idempotent=False)
    assert calls["n"] == 1


async def test_non_idempotent_still_retries_what_meta_rejected_explicitly():
    """``130429`` es "no lo procesé": reintentarlo no puede duplicar nada."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(
                429, json={"error": {"message": "throughput", "code": 130429}}
            )
        return httpx.Response(200, json={"messages": [{"id": "wamid.OK"}]})

    t = _transport_with(handler, max_retries=3)
    out = await t.request("POST", "/pnid/messages", access_token="tok", idempotent=False)
    assert out["messages"][0]["id"] == "wamid.OK"
    assert calls["n"] == 3


async def test_messages_client_marks_sends_as_non_idempotent():
    """La regla no sirve de nada si el cliente de mensajes no la pide."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(504, json={"error": {"message": "gateway timeout"}})

    client = make_messages_client(handler, max_retries=3)
    with pytest.raises(WaServerError):
        await client.send_text("573000000000", "hola", phone_number_id="PNID")
    assert calls["n"] == 1
