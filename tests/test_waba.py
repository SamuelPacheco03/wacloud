"""Tests de la suscripción de webhooks y los datos de la WABA."""

import httpx
import pytest

from tests.factories import capturing_handler, make_resolver, make_transport, ok_handler
from wacloud.waba import SubscribedApp, WabaClient, WabaInfo


def _client(handler) -> WabaClient:
    return WabaClient(make_transport(handler), make_resolver())


# --- Modelos -----------------------------------------------------------------


def test_waba_info_parses_meta_response():
    info = WabaInfo.from_meta(
        {
            "id": 102290129340398,
            "name": "Lucky Shrub",
            "timezone_id": "1",
            "currency": "EUR",
            "account_review_status": "APPROVED",
            "message_template_namespace": "abc_namespace",
        }
    )
    assert info.id == "102290129340398", "Meta devuelve el id como número"
    assert info.is_approved is True


def test_waba_not_approved():
    """Una WABA sin aprobar acepta configuración pero no mensajea en producción."""
    assert WabaInfo.from_meta({"account_review_status": "PENDING"}).is_approved is False


def test_subscribed_app_unwraps_the_nested_payload():
    """Meta anida los datos de la app bajo ``whatsapp_business_api_data``."""
    app = SubscribedApp.from_meta(
        {
            "whatsapp_business_api_data": {
                "id": 1234567890,
                "name": "Mi App",
                "link": "https://www.facebook.com/games/?app_id=1234567890",
            },
            "override_callback_uri": "https://host.example/webhook/empresa-1",
        }
    )
    assert app.app_id == "1234567890"
    assert app.name == "Mi App"
    assert app.override_callback_uri == "https://host.example/webhook/empresa-1"


def test_subscribed_app_survives_a_missing_payload():
    assert SubscribedApp.from_meta({"algo": "raro"}).app_id is None


# --- Consulta ----------------------------------------------------------------


async def test_get_requests_explicit_fields():
    captured, handler = capturing_handler({"id": "WABA", "name": "Lucky Shrub"})
    info = await _client(handler).get("WABA")

    assert info.name == "Lucky Shrub"
    assert captured["path"].endswith("/WABA")
    assert "account_review_status" in captured["params"]["fields"]


# --- Suscripción -------------------------------------------------------------


async def test_subscribe_posts_to_subscribed_apps():
    captured, handler = capturing_handler({"success": True})
    assert await _client(handler).subscribe("WABA") is True

    assert captured["method"] == "POST"
    assert captured["path"].endswith("/WABA/subscribed_apps")


async def test_subscribe_without_override_sends_no_params():
    """Sin callback propio, Meta usa el de la app: no hay nada que mandar."""
    captured, handler = capturing_handler({"success": True})
    await _client(handler).subscribe("WABA")
    assert captured["params"] == {}


async def test_subscribe_with_override_sends_uri_and_token():
    captured, handler = capturing_handler({"success": True})
    await _client(handler).subscribe(
        "WABA",
        override_callback_uri="https://host.example/webhook/empresa-1",
        verify_token="secreto",
    )
    assert captured["params"]["override_callback_uri"] == (
        "https://host.example/webhook/empresa-1"
    )
    assert captured["params"]["verify_token"] == "secreto"


async def test_override_without_verify_token_is_rejected_locally():
    """Meta verifica la URL con un GET de hub.challenge: sin token no la acepta."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"success": True})

    with pytest.raises(ValueError, match="exige 'verify_token'"):
        await _client(handler).subscribe("WABA", override_callback_uri="https://x")
    assert calls["n"] == 0


async def test_verify_token_alone_is_rejected():
    with pytest.raises(ValueError, match="solo aplica junto a"):
        await _client(ok_handler()).subscribe("WABA", verify_token="secreto")


async def test_list_subscriptions_returns_the_apps():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [
                    {"whatsapp_business_api_data": {"id": "1", "name": "A"}},
                    {"whatsapp_business_api_data": {"id": "2", "name": "B"}},
                ]
            },
        )

    apps = await _client(handler).list_subscriptions("WABA")
    assert [a.app_id for a in apps] == ["1", "2"]


async def test_list_subscriptions_survives_an_empty_body():
    """Una WABA sin suscripciones es el caso que más se consulta al depurar."""
    assert await _client(ok_handler({})).list_subscriptions("WABA") == []


async def test_unsubscribe_uses_delete():
    captured, handler = capturing_handler({"success": True})
    assert await _client(handler).unsubscribe("WABA") is True

    assert captured["method"] == "DELETE"
    assert captured["path"].endswith("/WABA/subscribed_apps")


async def test_success_false_is_reported():
    assert await _client(ok_handler({"success": False})).subscribe("WABA") is False
