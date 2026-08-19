"""Tests de los componentes de creación de plantillas.

El foco está en la forma exacta del campo ``example``: es asimétrica entre cabecera y
cuerpo, y equivocarse ahí es el motivo de rechazo más común. Cada aserción de forma se
contrasta con los ejemplos publicados por Meta.
"""

import pytest

from wacloud.templates import buttons, components
from wacloud.templates.enums import HeaderFormat, OtpType

# --- Forma del example: lo que más rechazos causa ----------------------------


def test_positional_body_example_is_a_list_of_lists():
    """Meta espera ``[["a", "b"]]`` en el cuerpo: doble corchete."""
    component = components.body(
        "Hola {{1}}, tu pedido {{2}} va en camino.", examples=["Ana", "A-123"]
    )
    assert component["example"] == {"body_text": [["Ana", "A-123"]]}


def test_positional_header_example_is_a_flat_list():
    """La cabecera usa ``["a"]``, sin anidar. Esta asimetría es la trampa clásica."""
    component = components.text_header("Pedido {{1}}", examples=["A-123"])
    assert component["example"] == {"header_text": ["A-123"]}


def test_named_body_example_is_a_list_of_objects():
    component = components.body(
        "Hola {{name}}, pedido {{order}} confirmado.",
        examples={"name": "Ana", "order": "A-123"},
    )
    assert component["example"] == {
        "body_text_named_params": [
            {"param_name": "name", "example": "Ana"},
            {"param_name": "order", "example": "A-123"},
        ]
    }


def test_named_header_uses_its_own_key():
    component = components.text_header("Pedido {{order}}", examples={"order": "A-1"})
    assert "header_text_named_params" in component["example"]


def test_named_examples_follow_text_order_not_dict_order():
    """El orden que importa es el del texto: un dict no garantiza el mismo."""
    component = components.body(
        "Hola {{primero}}, luego {{segundo}} y ya está.",
        examples={"segundo": "B", "primero": "A"},
    )
    names = [p["param_name"] for p in component["example"]["body_text_named_params"]]
    assert names == ["primero", "segundo"]


def test_media_header_uses_handle_not_media_id():
    component = components.media_header(HeaderFormat.IMAGE, handle="4::aW1h")
    assert component == {
        "type": "HEADER",
        "format": "IMAGE",
        "example": {"header_handle": ["4::aW1h"]},
    }


def test_location_header_has_no_example():
    """Las coordenadas se pasan al enviar, no al crear."""
    assert components.location_header() == {"type": "HEADER", "format": "LOCATION"}


# --- Validación de ejemplos --------------------------------------------------


def test_body_requires_examples_when_it_has_variables():
    with pytest.raises(ValueError, match="exige un ejemplo"):
        components.body("Hola {{1}}, qué tal todo.")


def test_body_rejects_examples_when_it_has_no_variables():
    with pytest.raises(ValueError, match="sobran los ejemplos"):
        components.body("Sin variables", examples=["Ana"])


def test_body_rejects_wrong_example_count():
    with pytest.raises(ValueError, match="2 variables y se dieron 1"):
        components.body("Hola {{1}} y {{2}}, buenas.", examples=["Ana"])


def test_named_body_rejects_missing_example():
    with pytest.raises(ValueError, match="falta el ejemplo"):
        components.body("Hola {{a}} y {{b}} ya.", examples={"a": "1"})


def test_named_body_rejects_unknown_example():
    with pytest.raises(ValueError, match="no aparece en el texto"):
        components.body("Hola {{a}} ya.", examples={"a": "1", "z": "9"})


def test_named_text_rejects_positional_examples():
    with pytest.raises(ValueError, match="deben ser un dict"):
        components.body("Hola {{name}} ya.", examples=["Ana"])


def test_positional_text_rejects_named_examples():
    with pytest.raises(ValueError, match="una lista ordenada"):
        components.body("Hola {{1}} ya.", examples={"1": "Ana"})


# --- Reglas de Meta por componente -------------------------------------------


def test_header_allows_only_one_variable():
    with pytest.raises(ValueError, match="admite 1 variable"):
        components.text_header("{{1}} y {{2}}", examples=["a", "b"])


def test_body_cannot_end_with_a_variable():
    """Meta: *the message template cannot start or end with a parameter*."""
    with pytest.raises(ValueError, match="no puede terminar"):
        components.body("Tu código es {{1}}", examples=["123"])


def test_body_cannot_start_with_a_variable():
    with pytest.raises(ValueError, match="no puede empezar"):
        components.body("{{1}} es tu código de acceso", examples=["123"])


def test_header_may_end_with_a_variable():
    """La regla de límites no se aplica a la cabecera: Meta aprueba 'Pedido {{1}}'."""
    assert components.text_header("Pedido {{1}}", examples=["A-1"])["text"]


def test_footer_rejects_variables():
    with pytest.raises(ValueError, match="no admite variables"):
        components.footer("Escríbenos {{1}}")


def test_footer_enforces_length():
    with pytest.raises(ValueError, match="máximo 60"):
        components.footer("x" * 61)


def test_header_enforces_length():
    with pytest.raises(ValueError, match="máximo 60"):
        components.text_header("x" * 61)


def test_body_enforces_length():
    with pytest.raises(ValueError, match="máximo 1024"):
        components.body("x" * 1025)


# --- Componentes de plantillas de autenticación ------------------------------


def test_auth_body_omits_text_because_meta_generates_it():
    assert components.body("", add_security_recommendation=True) == {
        "type": "BODY",
        "add_security_recommendation": True,
    }


def test_auth_body_rejects_explicit_text():
    with pytest.raises(ValueError, match="lo genera Meta"):
        components.body("Mi texto", add_security_recommendation=True)


def test_auth_footer_uses_expiration_minutes():
    assert components.footer(code_expiration_minutes=15) == {
        "type": "FOOTER",
        "code_expiration_minutes": 15,
    }


@pytest.mark.parametrize("minutes", [0, 91])
def test_auth_footer_rejects_expiration_out_of_range(minutes):
    with pytest.raises(ValueError, match="entre 1 y 90"):
        components.footer(code_expiration_minutes=minutes)


# --- Agrupación de botones ---------------------------------------------------


def test_buttons_rejects_more_than_ten():
    items = [buttons.quick_reply(f"b{i}") for i in range(11)]
    with pytest.raises(ValueError, match="máximo 10"):
        components.buttons(items)


def test_buttons_rejects_three_url_buttons():
    items = [buttons.url(f"u{i}", f"https://x.com/{i}") for i in range(3)]
    with pytest.raises(ValueError, match="2 botón\\(es\\) de tipo URL"):
        components.buttons(items)


def test_buttons_rejects_two_phone_numbers():
    items = [buttons.phone_number("a", "+341"), buttons.phone_number("b", "+342")]
    with pytest.raises(ValueError, match="tipo PHONE_NUMBER"):
        components.buttons(items)


def test_quick_replies_must_be_grouped():
    """Meta exige dos bloques: respuestas rápidas y el resto, sin intercalar."""
    items = [
        buttons.quick_reply("uno"),
        buttons.url("ver", "https://x.com"),
        buttons.quick_reply("dos"),
    ]
    with pytest.raises(ValueError, match="agrupados"):
        components.buttons(items)


def test_quick_replies_grouped_at_the_end_are_valid():
    items = [
        buttons.url("ver", "https://x.com"),
        buttons.quick_reply("uno"),
        buttons.quick_reply("dos"),
    ]
    assert len(components.buttons(items)["buttons"]) == 3


def test_only_quick_replies_is_valid():
    items = [buttons.quick_reply("uno"), buttons.quick_reply("dos")]
    assert len(components.buttons(items)["buttons"]) == 2


def test_buttons_requires_at_least_one():
    with pytest.raises(ValueError, match="al menos un botón"):
        components.buttons([])


# --- Botones individuales ----------------------------------------------------


def test_url_button_example_is_a_flat_list_on_the_button():
    """El ejemplo del botón no se envuelve en un objeto ``example``."""
    button = buttons.url("Ver", "https://x.com/o/{{1}}", example="A-1")
    assert button["example"] == ["A-1"]


def test_url_button_requires_example_when_it_has_a_variable():
    with pytest.raises(ValueError, match="'example' es obligatorio"):
        buttons.url("Ver", "https://x.com/o/{{1}}")


def test_url_button_rejects_example_without_variable():
    with pytest.raises(ValueError, match="sobra 'example'"):
        buttons.url("Ver", "https://x.com/o", example="A-1")


def test_url_button_variable_must_be_at_the_end():
    with pytest.raises(ValueError, match="al final"):
        buttons.url("Ver", "https://x.com/{{1}}/detalle", example="A-1")


def test_url_button_rejects_two_variables():
    with pytest.raises(ValueError, match="una sola variable"):
        buttons.url("Ver", "https://x.com/{{1}}/{{2}}", example="A-1")


def test_copy_code_example_is_a_bare_string():
    """A diferencia del resto de ejemplos, este no va en un array."""
    assert buttons.copy_code("VERANO20") == {
        "type": "COPY_CODE",
        "example": "VERANO20",
    }


def test_otp_one_tap_requires_supported_apps():
    with pytest.raises(ValueError, match="exige 'supported_apps'"):
        buttons.otp(OtpType.ONE_TAP)


def test_otp_copy_code_rejects_supported_apps():
    with pytest.raises(ValueError, match="no admite"):
        buttons.otp(
            OtpType.COPY_CODE,
            supported_apps=[{"package_name": "a", "signature_hash": "b"}],
        )


def test_otp_button_has_no_text_because_meta_generates_it():
    button = buttons.otp(OtpType.COPY_CODE)
    assert "text" not in button and button["otp_type"] == "COPY_CODE"


def test_otp_validates_app_fields():
    with pytest.raises(ValueError, match="package_name"):
        buttons.otp(OtpType.ZERO_TAP, supported_apps=[{"package_name": "solo"}])


def test_flow_button_requires_exactly_one_reference():
    with pytest.raises(ValueError, match="exactamente uno"):
        buttons.flow("Reservar")
    with pytest.raises(ValueError, match="exactamente uno"):
        buttons.flow("Reservar", flow_id="1", flow_name="dos")


def test_flow_button_uses_the_shorter_label_limit():
    with pytest.raises(ValueError, match="máximo 20"):
        buttons.flow("x" * 21, flow_id="1")


def test_button_label_limit_is_25_for_regular_buttons():
    with pytest.raises(ValueError, match="máximo 25"):
        buttons.quick_reply("x" * 26)


def test_voice_call_ttl_range():
    with pytest.raises(ValueError, match="entre 1440 y 43200"):
        buttons.voice_call("Llamar", ttl_minutes=10)
    assert buttons.voice_call("Llamar", ttl_minutes=1440)["ttl_minutes"] == 1440


# --- Botones simples ---------------------------------------------------------


@pytest.mark.parametrize(
    ("factory", "expected_type"),
    [
        (buttons.catalog, "CATALOG"),
        (buttons.mpm, "MPM"),
        (buttons.spm, "SPM"),
    ],
)
def test_commerce_buttons_have_default_labels(factory, expected_type):
    button = factory()
    assert button["type"] == expected_type
    assert button["text"]


def test_order_details_button():
    assert buttons.order_details("Pagar") == {
        "type": "ORDER_DETAILS",
        "text": "Pagar",
    }


def test_call_permission_request_button():
    assert buttons.call_permission_request("Permitir llamada")["type"] == (
        "REQUEST_CALL_PERMISSION"
    )


def test_voice_call_button_without_ttl():
    assert "ttl_minutes" not in buttons.voice_call("Llamar")


def test_flow_button_with_navigation_and_icon():
    button = buttons.flow(
        "Reservar",
        flow_id="123",
        navigate_screen="APPOINTMENT",
        icon="PROMOTION",
    )
    assert button["flow_id"] == "123"
    assert button["flow_action"] == "navigate"
    assert button["navigate_screen"] == "APPOINTMENT"
    assert button["icon"] == "PROMOTION"


def test_flow_button_accepts_flow_json():
    assert "flow_json" in buttons.flow("Ir", flow_json='{"screens":[]}')


@pytest.mark.parametrize("factory", [buttons.quick_reply, buttons.catalog])
def test_buttons_reject_empty_label(factory):
    with pytest.raises(ValueError, match="obligatorio"):
        factory("   ")


def test_phone_button_requires_a_number():
    with pytest.raises(ValueError, match="teléfono es obligatorio"):
        buttons.phone_number("Llamar", "")


def test_url_button_requires_a_url():
    with pytest.raises(ValueError, match="URL del botón es obligatoria"):
        buttons.url("Ver", "")


def test_copy_code_requires_an_example():
    with pytest.raises(ValueError, match="código de ejemplo es obligatorio"):
        buttons.copy_code("")


def test_media_header_rejects_text_format():
    with pytest.raises(ValueError, match="no es un formato de medio"):
        components.media_header(HeaderFormat.TEXT, handle="x")


def test_media_header_requires_a_handle():
    with pytest.raises(ValueError, match="Resumable Upload"):
        components.media_header(HeaderFormat.IMAGE, handle="")
