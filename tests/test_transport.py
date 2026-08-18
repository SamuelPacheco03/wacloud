"""Tests del transporte con httpx.MockTransport (sin red real)."""
import httpx
import pytest

from wacloud.config import GraphConfig
from wacloud.errors import WaInvalidRequest, WaRateLimited, WaServerError
from wacloud.transport import Transport


def _transport_with(handler, **config_overrides) -> Transport:
    # backoff a 0 para que los tests no esperen.
    config = GraphConfig(
        backoff_base_seconds=0.0,
        backoff_max_seconds=0.0,
        **config_overrides,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return Transport(config, client=client)


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
        backoff_base_seconds=0.0,
        backoff_max_seconds=0.0,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    t = Transport(config, client=client)
    await t.request("POST", "/123/messages", access_token="tok")
    assert captured["url"] == "https://graph.facebook.com/v20.0/123/messages"
