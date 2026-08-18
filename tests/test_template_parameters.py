"""Tests de los parámetros de envío de una plantilla aprobada."""

import httpx
import pytest

from tests.factories import make_templates_client, make_transport
from wacloud.credentials import StaticCredentialResolver, WaCredentials
from wacloud.templates import buttons, components, parameters
from wacloud.templates.client import TemplatesClient
from wacloud.templates.enums import TemplateCategory

# --- Formas de los parámetros ------------------------------------------------


def test_text_parameter_is_positional_by_default():
    assert parameters.text("Ana") == {"type": "text", "text": "Ana"}


def test_named_text_parameter_carries_parameter_name():
    assert parameters.text("Ana", name="first_name") == {
        "type": "text",
        "parameter_name": "first_name",
        "text": "Ana",
    }


def test_currency_uses_amount_1000():
    """100,99 se manda como 100990: el importe va multiplicado por mil."""
    param = parameters.currency(fallback_value="100,99 €", code="EUR", amount_1000=100990)
    assert param["currency"]["amount_1000"] == 100990
    assert param["currency"]["code"] == "EUR"


def test_date_time_only_sends_fallback_value():
    """Meta solo honra ``fallback_value``; el desglose daría falsa localización."""
    param = parameters.date_time("12 de septiembre")
    assert param["date_time"] == {"fallback_value": "12 de septiembre"}


def test_media_parameter_prefers_media_id():
    assert parameters.image(link="https://x/y.png", media_id="MID")["image"] == {"id": "MID"}


def test_media_parameter_falls_back_to_link():
    assert parameters.image(link="https://x/y.png")["image"] == {"link": "https://x/y.png"}


def test_media_parameter_requires_one_source():
    with pytest.raises(ValueError, match="'link' o 'media_id'"):
        parameters.image()


def test_document_parameter_carries_filename():
    param = parameters.document(media_id="MID", filename="recibo.pdf")
    assert param["document"]["filename"] == "recibo.pdf"


def test_location_parameter_shape():
    param = parameters.location(
        latitude="37.44", longitude="-122.16", name="Philz", address="101 Forest Ave"
    )
    assert param["location"]["latitude"] == "37.44"


# --- Componentes de envío ----------------------------------------------------


def test_body_component_wraps_parameters():
    assert parameters.body([parameters.text("Ana")]) == {
        "type": "body",
        "parameters": [{"type": "text", "text": "Ana"}],
    }


def test_button_index_is_a_string_and_subtype_lowercase():
    """Meta se contradice en sus docs; aquí siempre string y minúscula."""
    button = parameters.button_url(0, "A-123")
    assert button["index"] == "0"
    assert button["sub_type"] == "url"
    assert button["type"] == "button"


def test_button_url_parameter_is_text():
    assert parameters.button_url(1, "A-123")["parameters"] == [
        {"type": "text", "text": "A-123"}
    ]


def test_button_quick_reply_parameter_is_payload():
    assert parameters.button_quick_reply(0, "CANCELAR")["parameters"] == [
        {"type": "payload", "payload": "CANCELAR"}
    ]


def test_button_copy_code_parameter_is_coupon_code():
    assert parameters.button_copy_code(0, "VERANO20")["parameters"] == [
        {"type": "coupon_code", "coupon_code": "VERANO20"}
    ]


def test_button_flow_carries_token():
    param = parameters.button_flow(0, flow_token="T1", flow_action_data={"k": "v"})
    action = param["parameters"][0]["action"]
    assert action == {"flow_token": "T1", "flow_action_data": {"k": "v"}}


@pytest.mark.parametrize("index", [-1, 10])
def test_button_index_range(index):
    with pytest.raises(ValueError, match="entre 0 y 9"):
        parameters.button_url(index, "x")


# --- Integración con el cliente ----------------------------------------------


def _resolver():
    return StaticCredentialResolver(
        WaCredentials(phone_number_id="PNID", access_token="tok", waba_id="WABA")
    )


async def test_create_sends_validated_definition():
    captured = {}

    def handler(request):
        import json

        captured["body"] = json.loads(request.content.decode())
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"id": "123", "status": "PENDING"})

    client = TemplatesClient(make_transport(handler), _resolver())
    info = await client.create(
        "WABA",
        name="order_confirmation",
        language="es_ES",
        category=TemplateCategory.UTILITY,
        components=[components.body("Hola {{1}}, tu pedido va en camino.", examples=["Ana"])],
    )

    assert info.id == "123" and info.status == "PENDING"
    assert captured["url"].endswith("/WABA/message_templates")
    assert captured["body"]["parameter_format"] == "POSITIONAL"
    assert captured["body"]["components"][0]["example"] == {"body_text": [["Ana"]]}


async def test_create_rejects_invalid_template_before_calling_meta():
    """Meta limita a 100 creaciones por hora: no se gasta cupo en algo inválido."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={})

    client = TemplatesClient(make_transport(handler), _resolver())
    with pytest.raises(ValueError, match="nombre inválido"):
        await client.create(
            "WABA",
            name="Order Confirmation",
            language="es_ES",
            category=TemplateCategory.UTILITY,
            components=[components.body("Hola, qué tal.")],
        )
    assert calls["n"] == 0


async def test_create_rejects_template_without_body():
    client = make_templates_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="componente BODY"):
        await client.create(
            "WABA",
            name="sin_cuerpo",
            language="es_ES",
            category=TemplateCategory.MARKETING,
            components=[components.buttons([buttons.quick_reply("Hola")])],
        )
