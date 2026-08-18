"""Tests de validación de variables y de ensamblado de la plantilla completa."""

import pytest

from wacloud.templates import buttons, components
from wacloud.templates.definition import (
    build_definition,
    detect_parameter_format,
    validate_name,
)
from wacloud.templates.enums import ParameterFormat, TemplateCategory
from wacloud.templates.placeholders import analyze, detect_format, find_placeholders

# --- Análisis de variables ---------------------------------------------------


def test_finds_placeholders_in_order():
    assert find_placeholders("Hola {{1}} y {{2}}") == ["1", "2"]


def test_tolerates_inner_spaces():
    assert find_placeholders("Hola {{ nombre }}") == ["nombre"]


def test_detects_positional_and_named():
    assert detect_format("Hola {{1}}") is ParameterFormat.POSITIONAL
    assert detect_format("Hola {{nombre}}") is ParameterFormat.NAMED
    assert detect_format("Sin variables") is None


def test_rejects_mixed_formats():
    with pytest.raises(ValueError, match="mezcla variables"):
        detect_format("Hola {{1}} y {{nombre}}")


def test_positional_variables_must_start_at_one():
    with pytest.raises(ValueError, match="empezar en"):
        analyze("Hola {{2}} y {{3}} ya", field="body")


def test_positional_variables_must_be_consecutive():
    with pytest.raises(ValueError, match="no son consecutivas"):
        analyze("Hola {{1}} y {{3}} ya", field="body")


def test_repeating_a_variable_is_allowed():
    """Repetir ``{{1}}`` no añade un parámetro más."""
    fmt, variables = analyze("Hola {{1}}, adiós {{1}} otra vez", field="body")
    assert fmt is ParameterFormat.POSITIONAL
    assert variables == ["1"]


def test_rejects_unbalanced_braces():
    with pytest.raises(ValueError, match="sin cerrar"):
        analyze("Hola {{1} ya", field="body")


def test_rejects_empty_variable():
    with pytest.raises(ValueError, match="variable vacía"):
        analyze("Hola {{}} ya", field="body")


@pytest.mark.parametrize("name", ["Nombre", "con espacio", "con-guion", "1empieza"])
def test_rejects_invalid_named_parameters(name):
    with pytest.raises(ValueError, match="no es un nombre válido"):
        analyze(f"Hola {{{{{name}}}}} ya", field="body")


@pytest.mark.parametrize("name", ["nombre", "order_number", "campo_2", "_privado"])
def test_accepts_valid_named_parameters(name):
    fmt, variables = analyze(f"Hola {{{{{name}}}}} ya", field="body")
    assert fmt is ParameterFormat.NAMED and variables == [name]


# --- Nombre de la plantilla --------------------------------------------------


@pytest.mark.parametrize("name", ["order_confirmation", "promo_2024", "abc"])
def test_accepts_valid_names(name):
    assert validate_name(name) == name


@pytest.mark.parametrize("name", ["Order", "con espacio", "con-guion", "acentuación"])
def test_rejects_invalid_names(name):
    with pytest.raises(ValueError, match="nombre inválido"):
        validate_name(name)


def test_rejects_empty_name():
    with pytest.raises(ValueError, match="obligatorio"):
        validate_name("  ")


# --- Ensamblado --------------------------------------------------------------


def _body(text="Hola, todo listo por aquí."):
    return components.body(text)


def test_requires_a_body_component():
    with pytest.raises(ValueError, match="necesita un componente BODY"):
        build_definition(
            name="x",
            language="es_ES",
            category=TemplateCategory.UTILITY,
            components=[components.footer("pie")],
        )


def test_rejects_duplicate_components():
    with pytest.raises(ValueError, match="más de un componente BODY"):
        build_definition(
            name="x",
            language="es_ES",
            category=TemplateCategory.UTILITY,
            components=[_body(), _body()],
        )


def test_rejects_unknown_component_type():
    with pytest.raises(ValueError, match="desconocido"):
        build_definition(
            name="x",
            language="es_ES",
            category=TemplateCategory.UTILITY,
            components=[_body(), {"type": "INVENTADO"}],
        )


def test_infers_parameter_format_from_components():
    definition = build_definition(
        name="x",
        language="es_ES",
        category=TemplateCategory.UTILITY,
        components=[components.body("Hola {{name}}, ya está.", examples={"name": "A"})],
    )
    assert definition["parameter_format"] == "NAMED"


def test_omits_parameter_format_when_there_are_no_variables():
    definition = build_definition(
        name="x",
        language="es_ES",
        category=TemplateCategory.UTILITY,
        components=[_body()],
    )
    assert "parameter_format" not in definition


def test_rejects_declared_format_that_contradicts_components():
    with pytest.raises(ValueError, match="se declaró parameter_format=POSITIONAL"):
        build_definition(
            name="x",
            language="es_ES",
            category=TemplateCategory.UTILITY,
            components=[components.body("Hola {{name}}, ya.", examples={"name": "A"})],
            parameter_format=ParameterFormat.POSITIONAL,
        )


def test_rejects_header_and_body_with_different_formats():
    """Meta admite un formato por plantilla, no uno por componente."""
    mixed = [
        components.text_header("Pedido {{1}}", examples=["A-1"]),
        components.body("Hola {{name}}, ya está.", examples={"name": "Ana"}),
    ]
    with pytest.raises(ValueError, match="formatos de variable distintos"):
        detect_parameter_format(mixed)


def test_accepts_matching_formats_across_components():
    consistent = [
        components.text_header("Pedido {{1}}", examples=["A-1"]),
        components.body("Hola {{1}}, ya está listo.", examples=["Ana"]),
    ]
    assert detect_parameter_format(consistent) is ParameterFormat.POSITIONAL


def test_media_header_does_not_set_a_parameter_format():
    """El ``header_handle`` no es una variable: no debe forzar un formato."""
    comps = [components.media_header("IMAGE", handle="4::x"), _body()]
    assert detect_parameter_format(comps) is None


def test_full_definition_shape():
    definition = build_definition(
        name="order_confirmation",
        language="es_ES",
        category="UTILITY",
        components=[
            components.text_header("Pedido {{1}}", examples=["A-1"]),
            components.body("Hola {{1}}, tu pedido va en camino.", examples=["Ana"]),
            components.footer("Lucky Shrub"),
            components.buttons([buttons.quick_reply("Cancelar")]),
        ],
        message_send_ttl_seconds=3600,
    )
    assert definition["name"] == "order_confirmation"
    assert definition["category"] == "UTILITY"
    assert definition["parameter_format"] == "POSITIONAL"
    assert definition["message_send_ttl_seconds"] == 3600
    assert [c["type"] for c in definition["components"]] == [
        "HEADER",
        "BODY",
        "FOOTER",
        "BUTTONS",
    ]
