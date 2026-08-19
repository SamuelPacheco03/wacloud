"""Constructores de componentes para la **creación** de plantillas.

Aquí se concentra la parte de la API de Meta que más rechazos provoca: la forma del
campo ``example``, que **no es la misma** en cada componente.

===========================  ==========================================
Componente                   Forma del ejemplo
===========================  ==========================================
Cabecera de texto (posic.)   ``{"header_text": ["Ana"]}``
Cabecera de texto (nombres)  ``{"header_text_named_params": [{...}]}``
Cabecera de medio            ``{"header_handle": ["4::aW1h..."]}``
Cuerpo (posicional)          ``{"body_text": [["Ana", "123"]]}``  ← doble corchete
Cuerpo (con nombres)         ``{"body_text_named_params": [{...}]}``
===========================  ==========================================

El cuerpo posicional lleva un array **dentro** de otro array porque Meta admite varios
juegos de ejemplos; el de cabecera, no. Esa asimetría es la fuente de error número uno,
así que aquí se genera sola: quien llama pasa una lista de valores y nada más.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/components
"""

from __future__ import annotations

import itertools
from typing import Any

from wacloud.limits import TemplateLimits, ensure_max_items, ensure_max_length
from wacloud.templates.enums import (
    MEDIA_HEADER_FORMATS,
    ButtonType,
    HeaderFormat,
    ParameterFormat,
)
from wacloud.templates.placeholders import analyze, require_no_placeholders

__all__ = [
    "body",
    "buttons",
    "footer",
    "location_header",
    "media_header",
    "text_header",
]

#: Ejemplos aceptados: lista (posicional) o mapa nombre→valor (con nombres).
Examples = "list[str] | dict[str, str] | None"

#: Cuántos botones de cada tipo admite Meta como máximo.
_BUTTON_QUOTAS = {
    ButtonType.URL.value: TemplateLimits.MAX_URL_BUTTONS,
    ButtonType.PHONE_NUMBER.value: TemplateLimits.MAX_PHONE_NUMBER_BUTTONS,
    ButtonType.COPY_CODE.value: TemplateLimits.MAX_COPY_CODE_BUTTONS,
    ButtonType.QUICK_REPLY.value: TemplateLimits.MAX_QUICK_REPLY_BUTTONS,
}


def _named_examples(
    variables: list[str], examples: dict[str, str], *, field: str
) -> list[dict[str, str]]:
    """Convierte ``{"nombre": "valor"}`` al array de objetos que espera Meta."""
    missing = [name for name in variables if name not in examples]
    if missing:
        raise ValueError(f"{field}: falta el ejemplo de {{{{{missing[0]}}}}}")
    extra = [name for name in examples if name not in variables]
    if extra:
        raise ValueError(
            f"{field}: se dio un ejemplo para {{{{{extra[0]}}}}}, que no aparece en el texto"
        )
    # Se respeta el orden de aparición en el texto, no el del diccionario.
    return [{"param_name": name, "example": str(examples[name])} for name in variables]


def _positional_examples(
    variables: list[str], examples: list[str], *, field: str
) -> list[str]:
    """Valida que haya un ejemplo por variable y los devuelve en orden."""
    if len(examples) != len(variables):
        raise ValueError(
            f"{field}: el texto tiene {len(variables)} variables "
            f"y se dieron {len(examples)} ejemplos"
        )
    return [str(value) for value in examples]


def _resolve_examples(
    text: str,
    examples: list[str] | dict[str, str] | None,
    *,
    field: str,
    check_boundaries: bool = False,
) -> tuple[ParameterFormat | None, list[str] | list[dict[str, str]]]:
    """Valida texto y ejemplos juntos y devuelve ``(formato, ejemplos normalizados)``.

    El formato se deduce del texto, no se pide: pasar ``{{1}}`` con ejemplos con nombre
    (o al revés) es un error que se detecta aquí en vez de en la revisión de Meta.
    """
    fmt, variables = analyze(text, field=field, check_boundaries=check_boundaries)

    if fmt is None:
        if examples:
            raise ValueError(f"{field}: no tiene variables, sobran los ejemplos")
        return None, []

    if not examples:
        raise ValueError(
            f"{field}: tiene {len(variables)} variable(s) y Meta exige un ejemplo "
            "para cada una"
        )

    if fmt is ParameterFormat.NAMED:
        if not isinstance(examples, dict):
            raise ValueError(
                f"{field}: el texto usa variables con nombre, "
                "los ejemplos deben ser un dict {nombre: valor}"
            )
        return fmt, _named_examples(variables, examples, field=field)

    if not isinstance(examples, list):
        raise ValueError(
            f"{field}: el texto usa variables posicionales, "
            "los ejemplos deben ser una lista ordenada"
        )
    return fmt, _positional_examples(variables, examples, field=field)


def text_header(
    text: str, *, examples: list[str] | dict[str, str] | None = None
) -> dict[str, Any]:
    """Cabecera de texto. Máximo 60 caracteres y **una sola variable**."""
    clean = str(text or "").strip()
    if not clean:
        raise ValueError("el texto de la cabecera es obligatorio")
    ensure_max_length(clean, TemplateLimits.HEADER_TEXT, field="header.text")

    fmt, resolved = _resolve_examples(clean, examples, field="header")
    component: dict[str, Any] = {
        "type": "HEADER",
        "format": HeaderFormat.TEXT.value,
        "text": clean,
    }
    if fmt is None:
        return component

    if len(resolved) > TemplateLimits.HEADER_TEXT_MAX_VARIABLES:
        raise ValueError(
            f"la cabecera admite {TemplateLimits.HEADER_TEXT_MAX_VARIABLES} variable, "
            f"tiene {len(resolved)}"
        )

    if fmt is ParameterFormat.NAMED:
        component["example"] = {"header_text_named_params": resolved}
    else:
        # Array plano, a diferencia del cuerpo.
        component["example"] = {"header_text": resolved}
    return component


def media_header(media_format: HeaderFormat | str, *, handle: str) -> dict[str, Any]:
    """Cabecera de imagen, vídeo o documento.

    ``handle`` **no es un media ID**: es el identificador que devuelve la Resumable
    Upload API (``wacloud.media.upload_resumable``). Un media ID de la Media API no vale
    aquí, y al revés tampoco. Meta usa dos sistemas distintos para crear y para enviar.
    """
    fmt = HeaderFormat(media_format)
    if fmt not in MEDIA_HEADER_FORMATS:
        raise ValueError(
            f"{fmt.value} no es un formato de medio; "
            f"use uno de {sorted(f.value for f in MEDIA_HEADER_FORMATS)}"
        )
    clean = str(handle or "").strip()
    if not clean:
        raise ValueError(
            "se requiere el 'handle' de la Resumable Upload API para una cabecera de medio"
        )
    return {
        "type": "HEADER",
        "format": fmt.value,
        "example": {"header_handle": [clean]},
    }


def location_header() -> dict[str, Any]:
    """Cabecera de ubicación.

    No lleva ``example``: las coordenadas se pasan al enviar, no al crear. Solo válida en
    plantillas de utilidad y marketing.
    """
    return {"type": "HEADER", "format": HeaderFormat.LOCATION.value}


def body(
    text: str,
    *,
    examples: list[str] | dict[str, str] | None = None,
    add_security_recommendation: bool | None = None,
) -> dict[str, Any]:
    """Cuerpo de la plantilla. Es el único componente obligatorio.

    Los ejemplos se dan como lista (``["Ana", "123"]``) si el texto usa ``{{1}}``, o como
    diccionario (``{"nombre": "Ana"}``) si usa ``{{nombre}}``. El anidamiento que espera
    Meta se genera aquí.

    ``add_security_recommendation`` es exclusivo de las plantillas de autenticación,
    donde el texto lo genera Meta y por eso ``text`` va vacío.
    """
    if add_security_recommendation is not None:
        if text:
            raise ValueError(
                "el cuerpo de una plantilla de autenticación lo genera Meta: "
                "no se envía 'text'"
            )
        return {"type": "BODY", "add_security_recommendation": add_security_recommendation}

    clean = str(text or "").strip()
    if not clean:
        raise ValueError("el cuerpo de la plantilla es obligatorio")
    ensure_max_length(clean, TemplateLimits.BODY, field="body.text")

    fmt, resolved = _resolve_examples(clean, examples, field="body", check_boundaries=True)
    component: dict[str, Any] = {"type": "BODY", "text": clean}
    if fmt is None:
        return component

    if fmt is ParameterFormat.NAMED:
        component["example"] = {"body_text_named_params": resolved}
    else:
        # Doble corchete: Meta admite varios juegos de ejemplos y espera una lista de
        # listas aunque solo se dé uno.
        component["example"] = {"body_text": [resolved]}
    return component


def footer(text: str = "", *, code_expiration_minutes: int | None = None) -> dict[str, Any]:
    """Pie de la plantilla. Máximo 60 caracteres y **sin variables**.

    ``code_expiration_minutes`` (de 1 a 90) es exclusivo de las plantillas de autenticación:
    Meta genera el texto del pie a partir de ese valor.
    """
    if code_expiration_minutes is not None:
        low, high = TemplateLimits.OTP_EXPIRATION_MINUTES
        if not low <= code_expiration_minutes <= high:
            raise ValueError(
                f"code_expiration_minutes debe estar entre {low} y {high}, "
                f"no {code_expiration_minutes}"
            )
        return {"type": "FOOTER", "code_expiration_minutes": code_expiration_minutes}

    clean = str(text or "").strip()
    if not clean:
        raise ValueError("el texto del pie es obligatorio")
    ensure_max_length(clean, TemplateLimits.FOOTER, field="footer.text")
    require_no_placeholders(clean, field="footer.text")
    return {"type": "FOOTER", "text": clean}


def _check_button_quotas(items: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for button in items:
        kind = str(button.get("type", ""))
        counts[kind] = counts.get(kind, 0) + 1
    for kind, quota in _BUTTON_QUOTAS.items():
        found = counts.get(kind, 0)
        if found > quota:
            raise ValueError(
                f"Meta admite {quota} botón(es) de tipo {kind}, se dieron {found}"
            )


def _check_button_grouping(items: list[dict[str, Any]]) -> None:
    """Meta exige que los botones de respuesta rápida vayan agrupados.

    Verbatim: *"If using quick reply buttons with other buttons, buttons must be
    organized into two groups: quick reply buttons and non-quick reply buttons"*. Es
    decir, no pueden ir intercalados.
    """
    is_quick = [b.get("type") == ButtonType.QUICK_REPLY.value for b in items]
    if not any(is_quick) or all(is_quick):
        return
    # Cuenta cuántas veces cambia el grupo: con dos bloques contiguos, cambia una vez.
    transitions = sum(1 for a, b in itertools.pairwise(is_quick) if a != b)
    if transitions > 1:
        raise ValueError(
            "los botones de respuesta rápida deben ir agrupados, no intercalados "
            "con los de otro tipo"
        )


def buttons(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Agrupa los botones en el componente ``BUTTONS``.

    Valida los cupos por tipo y la regla de agrupación. Aviso de usabilidad de Meta: con
    más de 3 botones WhatsApp muestra 2 y esconde el resto tras "Ver todas las opciones",
    y las plantillas con 4 o más botones no se ven en WhatsApp Desktop.
    """
    if not items:
        raise ValueError("se requiere al menos un botón")
    ensure_max_items(list(items), TemplateLimits.MAX_BUTTONS, field="buttons")
    _check_button_quotas(items)
    _check_button_grouping(items)
    return {"type": "BUTTONS", "buttons": list(items)}
