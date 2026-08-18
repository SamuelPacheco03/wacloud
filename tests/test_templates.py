"""Tests del módulo templates: builders + TemplatesClient con MockTransport."""
import httpx
import pytest

from wacloud.config import GraphConfig
from wacloud.credentials import StaticCredentialResolver, WaCredentials
from wacloud.messages import MessagesClient
from wacloud.templates import TemplatesClient, builders
from wacloud.transport import Transport


# --- Builders ---------------------------------------------------------------


def test_build_auth_copy_code_has_body_and_button_params():
    payload = builders.build_auth_copy_code("57300", "auth_x", "123456")
    comps = payload["template"]["components"]
    assert payload["type"] == "template"
    assert comps[0]["parameters"][0]["text"] == "123456"
    assert comps[1]["sub_type"] == "url"
    assert comps[1]["parameters"][0]["text"] == "123456"


def test_build_auth_basic_has_only_body():
    payload = builders.build_auth_basic("57300", "auth_basic", "999")
    comps = payload["template"]["components"]
    assert len(comps) == 1 and comps[0]["type"] == "body"


def test_build_marketing_requires_to_or_recipient():
    with pytest.raises(ValueError):
        builders.build_marketing_template(name="promo", language_code="es")


def test_build_marketing_normalizes_to():
    payload = builders.build_marketing_template(
        name="promo", language_code="es", to="+57 300 111 2233"
    )
    assert payload["to"] == "573001112233"
    assert payload["template"]["name"] == "promo"


# --- TemplatesClient --------------------------------------------------------


def _clients(handler, *, cache_ttl=60.0):
    config = GraphConfig(backoff_base_seconds=0.0, backoff_max_seconds=0.0)
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = Transport(config, client=http)
    resolver = StaticCredentialResolver(
        WaCredentials(phone_number_id="PNID", access_token="tok", waba_id="WABA")
    )
    templates = TemplatesClient(
        transport, resolver, config=config, cache_ttl_seconds=cache_ttl
    )
    messages = MessagesClient(transport, resolver, config=config)
    return templates, messages


async def test_create_posts_and_returns_info():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"id": "T1", "status": "PENDING", "category": "UTILITY"})

    templates, _ = _clients(handler)
    info = await templates.create(
        "WABA",
        name="recibo",
        language="es",
        category="UTILITY",
        components=[{"type": "BODY", "text": "Hola {{1}}"}],
    )
    assert info.id == "T1" and info.status == "PENDING"
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/WABA/message_templates")


async def test_list_caches_second_call():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"data": [{"id": "T1", "name": "recibo", "status": "APPROVED"}]},
        )

    templates, _ = _clients(handler)
    first = await templates.list("WABA")
    second = await templates.list("WABA")
    assert calls["n"] == 1  # la 2ª vino del cache
    assert first[0].name == "recibo" and second[0].name == "recibo"


async def test_list_cache_expires():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"data": []})

    templates, _ = _clients(handler, cache_ttl=0.0)
    await templates.list("WABA")
    await templates.list("WABA")
    assert calls["n"] == 2  # TTL 0 => siempre refresca


async def test_status_finds_by_name():
    def handler(request):
        return httpx.Response(
            200,
            json={"data": [{"name": "recibo", "status": "APPROVED"}]},
        )

    templates, _ = _clients(handler)
    assert await templates.status("WABA", "recibo") == "APPROVED"
    assert await templates.status("WABA", "inexistente") is None


async def test_delete_sends_name_param():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"success": True})

    templates, _ = _clients(handler)
    out = await templates.delete("WABA", name="recibo")
    assert out["success"] is True
    assert captured["method"] == "DELETE"
    assert "name=recibo" in captured["url"]


async def test_send_marketing_uses_marketing_endpoint():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"messages": [{"id": "wamid.M"}]})

    templates, _ = _clients(handler)
    result = await templates.send_marketing_template(
        phone_number_id="PNID", name="promo", language_code="es", to="573001112233"
    )
    assert result.message_id == "wamid.M"
    assert captured["url"].endswith("/PNID/marketing_messages")


async def test_send_template_uses_messages_endpoint():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"messages": [{"id": "wamid.T"}]})

    _, messages = _clients(handler)
    result = await messages.send_template(
        "573001112233", "recibo", "es", phone_number_id="PNID"
    )
    assert result.message_id == "wamid.T"
    assert captured["url"].endswith("/PNID/messages")
