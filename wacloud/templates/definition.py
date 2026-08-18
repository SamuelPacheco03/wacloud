"""Ensamblado y validación de la plantilla completa antes de enviarla a Meta.

Los builders de ``components`` validan cada pieza por separado. Aquí se comprueba lo que
solo se ve mirando el conjunto: que el nombre sea válido, que no haya componentes
repetidos, que exista cuerpo y que la cabecera y el cuerpo no usen formatos de variable
distintos.

Merece la pena hacerlo local: Meta limita la creación a 100 plantillas por hora y WABA
(código ``80008``), y un rechazo tarda minutos u horas en llegar por webhook.
"""

from __future__ import annotations

import re
from typing import Any

from wacloud.limits import TemplateLimits, ensure_max_length
from wacloud.templates.enums import ParameterFormat, TemplateCategory

#: Meta: minúsculas, dígitos y guiones bajos. Un nombre con mayúsculas o espacios
#: provoca un error 100 sin más explicación.
_TEMPLATE_NAME = re.compile(r"^[a-z0-9_]+$")

#: Un componente de cada tipo como máximo.
_COMPONENT_TYPES = ("HEADER", "BODY", "FOOTER", "BUTTONS", "CAROUSEL", "LIMITED_TIME_OFFER")

#: Claves de ``example`` que delatan el formato de las variables.
_NAMED_EXAMPLE_KEYS = ("header_text_named_params", "body_text_named_params")
_POSITIONAL_EXAMPLE_KEYS = ("header_text", "body_text")


def validate_name(name: str) -> str:
    """Valida el nombre de la plantilla y lo devuelve normalizado."""
    clean = str(name or "").strip()
    if not clean:
        raise ValueError("el nombre de la plantilla es obligatorio")
    ensure_max_length(clean, TemplateLimits.NAME, field="template.name")
    if not _TEMPLATE_NAME.match(clean):
        raise ValueError(
            f"nombre inválido: {clean!r}. Meta solo admite minúsculas, dígitos y "
            "guiones bajos (p. ej. 'order_confirmation_v2')"
        )
    return clean


def _component_format(component: dict[str, Any]) -> ParameterFormat | None:
    """Formato de variable que declara un componente, según su ``example``."""
    example = component.get("example")
    if not isinstance(example, dict):
        return None
    if any(key in example for key in _NAMED_EXAMPLE_KEYS):
        return ParameterFormat.NAMED
    if any(key in example for key in _POSITIONAL_EXAMPLE_KEYS):
        return ParameterFormat.POSITIONAL
    return None


def detect_parameter_format(
    components: list[dict[str, Any]],
) -> ParameterFormat | None:
    """Deduce el formato de la plantilla y verifica que sea coherente.

    Meta admite un solo formato por plantilla: una cabecera con ``{{1}}`` y un cuerpo con
    ``{{nombre}}`` es un rechazo seguro.
    """
    found = {fmt for fmt in (_component_format(c) for c in components) if fmt is not None}
    if len(found) > 1:
        raise ValueError(
            "la cabecera y el cuerpo usan formatos de variable distintos; "
            "Meta admite POSITIONAL o NAMED, pero no ambos en la misma plantilla"
        )
    return found.pop() if found else None


def _check_component_uniqueness(components: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for component in components:
        kind = str(component.get("type", "")).upper()
        if kind not in _COMPONENT_TYPES:
            raise ValueError(f"tipo de componente desconocido: {kind!r}")
        if kind in seen:
            raise ValueError(f"hay más de un componente {kind}: Meta admite uno")
        seen.add(kind)
    if "BODY" not in seen:
        raise ValueError("la plantilla necesita un componente BODY")


def build_definition(
    *,
    name: str,
    language: str,
    category: TemplateCategory | str,
    components: list[dict[str, Any]],
    parameter_format: ParameterFormat | str | None = None,
    message_send_ttl_seconds: int | None = None,
) -> dict[str, Any]:
    """Arma y valida el cuerpo de ``POST /{waba_id}/message_templates``.

    ``parameter_format`` se deduce de los componentes si no se indica. Indicarlo
    explícitamente sirve para detectar una discrepancia: si no coincide con lo que dicen
    los componentes, se lanza ``ValueError`` en vez de dejar que Meta rechace la plantilla.
    """
    if not components:
        raise ValueError("la plantilla necesita al menos un componente")
    _check_component_uniqueness(components)

    detected = detect_parameter_format(components)
    if parameter_format is not None:
        declared = ParameterFormat(parameter_format)
        if detected is not None and declared is not detected:
            raise ValueError(
                f"se declaró parameter_format={declared.value} pero los componentes "
                f"usan {detected.value}"
            )
        detected = declared

    payload: dict[str, Any] = {
        "name": validate_name(name),
        "language": str(language).strip(),
        "category": TemplateCategory(category).value,
        "components": list(components),
    }
    if detected is not None:
        payload["parameter_format"] = detected.value
    if message_send_ttl_seconds is not None:
        payload["message_send_ttl_seconds"] = message_send_ttl_seconds
    return payload
