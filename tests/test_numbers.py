"""Tests de la gestión del número: estado, registro, verificación y perfil."""

import httpx
import pytest

from tests.factories import (
    capturing_handler,
    make_resolver,
    make_transport,
    ok_handler,
)
from wacloud.numbers import BusinessVertical, CodeMethod, NumbersClient
from wacloud.numbers.models import BusinessProfile, PhoneNumberInfo


def _client(handler) -> NumbersClient:
    return NumbersClient(make_transport(handler), make_resolver())


def _ok(body=None):
    return capturing_handler(body or {"success": True})


# --- Modelos -----------------------------------------------------------------


def test_phone_number_info_parses_meta_response():
    info = PhoneNumberInfo.from_meta(
        {
            "id": 105954558954427,
            "display_phone_number": "15555555555",
            "verified_name": "Support Number",
            "quality_rating": "GREEN",
            "status": "CONNECTED",
            "code_verification_status": "VERIFIED",
        }
    )
    assert info.id == "105954558954427", "Meta devuelve el id como número"
    assert info.is_connected is True
    assert info.is_verified is True


def test_unknown_enum_values_do_not_break_parsing():
    """Meta discrepa consigo misma en la ortografía: no se fuerza a un Enum."""
    info = PhoneNumberInfo.from_meta(
        {"status": "DISCONNECTED", "code_verification_status": "UNVERIFIED"}
    )
    assert info.status == "DISCONNECTED"
    assert info.is_connected is False
    assert info.is_verified is False


def test_messaging_limit_prefers_the_current_field():
    info = PhoneNumberInfo.from_meta(
        {
            "whatsapp_business_manager_messaging_limit": "TIER_2K",
            "messaging_limit_tier": "TIER_250",
        }
    )
    assert info.messaging_limit == "TIER_2K"


def test_messaging_limit_falls_back_to_the_deprecated_field():
    info = PhoneNumberInfo.from_meta({"messaging_limit_tier": "TIER_250"})
    assert info.messaging_limit == "TIER_250"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(80, "80"), ({"level": "STANDARD"}, "STANDARD"), (None, None), ({}, None)],
)
def test_throughput_accepts_both_shapes_meta_has_used(raw, expected):
    assert PhoneNumberInfo.from_meta({"throughput": raw}).throughput == expected


def test_business_profile_unwraps_the_data_list():
    """Meta envuelve el perfil en una lista aunque solo haya uno."""
    profile = BusinessProfile.from_meta(
        {"data": [{"about": "Vivero", "websites": ["https://x.com"]}]}
    )
    assert profile.about == "Vivero"
    assert profile.websites == ["https://x.com"]


def test_business_profile_accepts_a_flat_body():
    assert BusinessProfile.from_meta({"about": "Vivero"}).about == "Vivero"


def test_business_profile_survives_a_malformed_body():
    assert BusinessProfile.from_meta({"data": ["no es un objeto"]}).about is None


# --- Consulta ----------------------------------------------------------------


async def test_get_requests_explicit_fields():
    """Sin ``fields`` Meta devuelve un subconjunto mínimo."""
    captured, handler = _ok({"id": "PNID", "quality_rating": "GREEN"})
    info = await _client(handler).get("PNID")

    assert info.quality_rating == "GREEN"
    assert "quality_rating" in captured["params"]["fields"]
    assert "whatsapp_business_manager_messaging_limit" in captured["params"]["fields"]


async def test_list_all_follows_pagination():
    pages = {"n": 0}

    def handler(request):
        pages["n"] += 1
        if pages["n"] == 1:
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "1", "display_phone_number": "+34600000001"}],
                    "paging": {"cursors": {"after": "CUR"}, "next": "https://x"},
                },
            )
        return httpx.Response(
            200, json={"data": [{"id": "2", "display_phone_number": "+34600000002"}]}
        )

    numbers = await _client(handler).list_all("WABA")
    assert [n.id for n in numbers] == ["1", "2"]
    assert pages["n"] == 2


async def test_list_all_stops_without_next():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(
            200, json={"data": [{"id": "1"}], "paging": {"cursors": {"after": "CUR"}}}
        )

    await _client(handler).list_all("WABA")
    assert calls["n"] == 1


# --- Registro y verificación -------------------------------------------------


async def test_register_sends_pin_and_messaging_product():
    captured, handler = _ok()
    assert await _client(handler).register("PNID", pin="123456") is True
    assert captured["path"].endswith("/PNID/register")
    assert captured["body"] == {"messaging_product": "whatsapp", "pin": "123456"}


async def test_register_accepts_a_valid_localization_region():
    captured, handler = _ok()
    await _client(handler).register("PNID", pin="123456", data_localization_region="de")
    assert captured["body"]["data_localization_region"] == "DE"


async def test_register_rejects_an_unsupported_region():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"success": True})

    with pytest.raises(ValueError, match="no es una región"):
        await _client(handler).register("PNID", pin="123456", data_localization_region="ES")
    assert calls["n"] == 0


@pytest.mark.parametrize("pin", ["12345", "1234567", "abcdef", "", "12 34 56"])
async def test_register_rejects_a_malformed_pin(pin):
    handler = ok_handler()
    with pytest.raises(ValueError, match="seis dígitos"):
        await _client(handler).register("PNID", pin=pin)


async def test_deregister_posts_to_the_right_endpoint():
    captured, handler = _ok()
    assert await _client(handler).deregister("PNID") is True
    assert captured["path"].endswith("/PNID/deregister")


async def test_set_two_step_pin():
    captured, handler = _ok()
    assert await _client(handler).set_two_step_pin("PNID", "654321") is True
    assert captured["body"] == {"pin": "654321"}


async def test_request_verification_code_defaults_to_sms():
    captured, handler = _ok()
    await _client(handler).request_verification_code("PNID")
    assert captured["path"].endswith("/PNID/request_code")
    assert captured["params"]["code_method"] == "SMS"


async def test_request_verification_code_accepts_voice():
    captured, handler = _ok()
    await _client(handler).request_verification_code(
        "PNID", method=CodeMethod.VOICE, language="en_US"
    )
    assert captured["params"]["code_method"] == "VOICE"
    assert captured["params"]["language"] == "en_US"


async def test_verify_code_sends_the_code():
    captured, handler = _ok()
    assert await _client(handler).verify_code("PNID", "000000") is True
    assert captured["params"]["code"] == "000000"


async def test_verify_code_requires_a_code():
    handler = ok_handler()
    with pytest.raises(ValueError, match="código de verificación es obligatorio"):
        await _client(handler).verify_code("PNID", "  ")


async def test_success_false_is_reported():
    _, handler = _ok({"success": False})
    assert await _client(handler).deregister("PNID") is False


# --- Perfil de negocio -------------------------------------------------------


async def test_get_profile_requests_explicit_fields():
    captured, handler = _ok({"data": [{"about": "Vivero de suculentas"}]})
    profile = await _client(handler).get_profile("PNID")

    assert profile.about == "Vivero de suculentas"
    assert "profile_picture_url" in captured["params"]["fields"]
    assert captured["path"].endswith("/PNID/whatsapp_business_profile")


async def test_update_profile_sends_only_the_given_fields():
    captured, handler = _ok()
    await _client(handler).update_profile(
        "PNID", about="Vivero", vertical=BusinessVertical.RETAIL
    )
    assert captured["body"] == {
        "messaging_product": "whatsapp",
        "about": "Vivero",
        "vertical": "RETAIL",
    }


async def test_update_profile_writes_a_handle_not_a_url():
    """Asimetría de Meta: se lee ``profile_picture_url`` y se escribe el handle."""
    captured, handler = _ok()
    await _client(handler).update_profile("PNID", profile_picture_handle="4::aW1h")
    assert captured["body"]["profile_picture_handle"] == "4::aW1h"


async def test_update_profile_accepts_an_empty_website_list():
    """Vaciar la lista es una operación legítima, no un 'campo sin indicar'."""
    captured, handler = _ok()
    await _client(handler).update_profile("PNID", websites=[])
    assert captured["body"]["websites"] == []


async def test_update_profile_rejects_an_unknown_vertical():
    handler = ok_handler()
    with pytest.raises(ValueError):
        await _client(handler).update_profile("PNID", vertical="FLORISTERIA")


async def test_update_profile_requires_at_least_one_field():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"success": True})

    with pytest.raises(ValueError, match="ningún campo"):
        await _client(handler).update_profile("PNID")
    assert calls["n"] == 0


async def test_update_profile_does_not_enforce_undocumented_length_limits():
    """Meta no publica hoy los límites del perfil: no se inventan en local."""
    captured, handler = _ok()
    await _client(handler).update_profile("PNID", about="x" * 500)
    assert len(captured["body"]["about"]) == 500
