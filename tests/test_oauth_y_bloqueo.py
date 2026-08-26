"""Tests del canje de Embedded Signup y del bloqueo de usuarios."""

import httpx
import pytest

from tests.factories import capturing_handler, make_resolver, make_transport, ok_handler
from wacloud.errors import WaTransportError
from wacloud.numbers import MAX_USERS_PER_CALL, BlockedUsersClient, BlockResult
from wacloud.oauth import OAuthClient
from wacloud.waba import BusinessToken

# --- Embedded Signup ---------------------------------------------------------


def _oauth(handler) -> OAuthClient:
    return OAuthClient(make_transport(handler), app_id="APPID", app_secret="SECRETO")


async def test_exchange_code_returns_the_token():
    captured, handler = capturing_handler({"access_token": "EAAtoken", "token_type": "bearer"})
    token = await _oauth(handler).exchange_code("CODE-123")

    assert token.access_token == "EAAtoken"
    assert token.token_type == "bearer"
    assert captured["path"].endswith("/oauth/access_token")


async def test_exchange_code_sends_app_credentials_and_code():
    captured, handler = capturing_handler({"access_token": "EAAtoken"})
    await _oauth(handler).exchange_code("CODE-123")

    assert captured["params"] == {
        "client_id": "APPID",
        "client_secret": "SECRETO",
        "code": "CODE-123",
    }


async def test_exchange_code_sends_no_bearer():
    """Las credenciales son el propio client_secret; un bearer aquí sería incoherente."""
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"access_token": "EAAtoken"})

    await _oauth(handler).exchange_code("CODE-123")
    assert seen["auth"] is None


async def test_exchange_code_is_not_retried_on_network_failure():
    """El código es de un solo uso: repetirlo tras un timeout no puede funcionar."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectTimeout("sin respuesta")

    client = OAuthClient(
        make_transport(handler, max_retries=3), app_id="APPID", app_secret="SECRETO"
    )
    with pytest.raises(WaTransportError):
        await client.exchange_code("CODE-123")
    assert calls["n"] == 1


async def test_exchange_code_requires_a_code():
    with pytest.raises(ValueError, match="código de Embedded Signup"):
        await _oauth(ok_handler()).exchange_code("  ")


@pytest.mark.parametrize(
    ("app_id", "app_secret"), [("", "SECRETO"), ("APPID", ""), ("  ", "  ")]
)
def test_oauth_client_requires_app_credentials(app_id, app_secret):
    with pytest.raises(ValueError, match="obligatorio"):
        OAuthClient(make_transport(ok_handler()), app_id=app_id, app_secret=app_secret)


def test_business_token_fails_loudly_without_a_token():
    with pytest.raises(ValueError, match="no devolvió un access_token"):
        BusinessToken.from_meta({"error": "algo"})


# --- Bloqueo de usuarios -----------------------------------------------------


def _blocking(handler) -> BlockedUsersClient:
    return BlockedUsersClient(make_transport(handler), make_resolver())


def test_block_result_separates_success_from_failure():
    """Meta responde por usuario: puede aceptar unos y rechazar otros."""
    result = BlockResult.from_meta(
        {
            "block_users": {
                "added_users": [{"input": "+57300", "wa_id": "57300"}],
                "failed_users": [{"input": "+57301", "errors": [{"code": 139100}]}],
            }
        },
        key="added_users",
    )
    assert result.succeeded == ["57300"]
    assert len(result.failed) == 1
    assert result.all_succeeded is False


def test_block_result_all_succeeded():
    result = BlockResult.from_meta(
        {"block_users": {"added_users": [{"wa_id": "57300"}]}}, key="added_users"
    )
    assert result.all_succeeded is True


async def test_block_normalizes_recipients():
    captured, handler = capturing_handler(
        {"block_users": {"added_users": [{"wa_id": "573001112233"}]}}
    )
    await _blocking(handler).block("PNID", ["+57 300 111 2233"])

    assert captured["path"].endswith("/PNID/block_users")
    assert captured["body"] == {
        "messaging_product": "whatsapp",
        "block_users": [{"user": "573001112233"}],
    }


async def test_unblock_uses_delete_and_reads_removed_users():
    captured, handler = capturing_handler(
        {"block_users": {"removed_users": [{"wa_id": "573001112233"}]}}
    )
    result = await _blocking(handler).unblock("PNID", ["573001112233"])

    assert captured["method"] == "DELETE"
    assert result.succeeded == ["573001112233"]


async def test_block_rejects_an_empty_list():
    with pytest.raises(ValueError, match="al menos un usuario"):
        await _blocking(ok_handler()).block("PNID", [])


async def test_block_rejects_more_than_the_meta_limit():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={})

    users = [f"57300111{i:04d}" for i in range(MAX_USERS_PER_CALL + 1)]
    with pytest.raises(ValueError, match="100 usuarios por llamada"):
        await _blocking(handler).block("PNID", users)
    assert calls["n"] == 0


async def test_list_blocked_follows_pagination():
    pages = {"n": 0}

    def handler(request):
        pages["n"] += 1
        if pages["n"] == 1:
            return httpx.Response(
                200,
                json={
                    "data": [{"wa_id": "1"}],
                    "paging": {"cursors": {"after": "CUR"}, "next": "https://x"},
                },
            )
        return httpx.Response(200, json={"data": [{"wa_id": "2"}]})

    assert await _blocking(handler).list_all("PNID") == ["1", "2"]
    assert pages["n"] == 2


async def test_list_blocked_survives_an_empty_body():
    assert await _blocking(ok_handler({})).list_all("PNID") == []
