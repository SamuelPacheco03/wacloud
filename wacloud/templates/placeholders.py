"""Análisis y validación de las variables (``{{...}}``) de una plantilla.

Meta rechaza plantillas por reglas que no se ven a simple vista, y el rechazo llega
minutos u horas después por webhook. Validar aquí convierte ese ciclo lento en un
``ValueError`` inmediato.

Reglas que aplica Meta, verbatim de su guía de revisión:

- *"Variable parameters are not sequential"* — deben empezar en 1 y no saltarse números.
- *"The message template cannot start or end with a parameter"*.
- Llaves desbalanceadas o variables con caracteres especiales (``#``, ``$``, ``%``).
- Los ``example`` son obligatorios en cuanto un componente tiene variables.

Regla que **no** se aplica: la creencia de que dos variables no pueden ser adyacentes
(``{{1}}{{2}}``) no aparece en ninguna página de Meta. No se valida algo que no está
documentado.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-review
"""

from __future__ import annotations

import re

from wacloud.templates.enums import ParameterFormat

#: Captura el contenido de cada ``{{...}}``, tolerando espacios interiores.
_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")

#: Nombre válido de una variable con ``parameter_format=NAMED``.
#:
#: Meta describe el formato en prosa —*"lowercase characters and underscores"*— y no
#: publica una expresión regular, así que no queda claro si admite dígitos. Se acepta el
#: superconjunto razonable (dígitos sí, pero no como primer carácter) porque rechazar un
#: nombre que Meta acepta sería peor que dejarlo pasar y que lo rechace Meta.
_NAMED_PARAM = re.compile(r"^[a-z_][a-z0-9_]*$")


def find_placeholders(text: str) -> list[str]:
    """Contenido de cada ``{{...}}``, en orden de aparición y con repeticiones."""
    return _PLACEHOLDER.findall(text or "")


def detect_format(text: str) -> ParameterFormat | None:
    """Deduce el formato de las variables del texto, o ``None`` si no tiene.

    Lanza ``ValueError`` si mezcla los dos formatos: Meta admite uno por plantilla.
    """
    found = find_placeholders(text)
    if not found:
        return None

    positional = [p for p in found if p.isdigit()]
    named = [p for p in found if not p.isdigit()]

    if positional and named:
        raise ValueError(
            "la plantilla mezcla variables posicionales y con nombre "
            f"({positional[0]!r} y {named[0]!r}); Meta admite un solo formato"
        )
    return ParameterFormat.POSITIONAL if positional else ParameterFormat.NAMED


def _check_unbalanced_braces(text: str, *, field: str) -> None:
    """Detecta ``{{`` sin su ``}}``, que Meta rechaza sin decir dónde."""
    without_placeholders = _PLACEHOLDER.sub("", text)
    if "{{" in without_placeholders or "}}" in without_placeholders:
        raise ValueError(f"{field}: hay llaves de variable sin cerrar")


def _check_boundaries(text: str, *, field: str) -> None:
    """Meta: *"The message template cannot start or end with a parameter"*."""
    stripped = text.strip()
    if not stripped:
        return
    if _PLACEHOLDER.match(stripped):
        raise ValueError(f"{field}: no puede empezar con una variable")
    match = _PLACEHOLDER.search(stripped)
    if match is not None:
        for candidate in _PLACEHOLDER.finditer(stripped):
            if candidate.end() == len(stripped):
                raise ValueError(f"{field}: no puede terminar con una variable")


def _check_positional_sequence(placeholders: list[str], *, field: str) -> int:
    """Valida que las variables sean ``1..n`` sin huecos. Devuelve ``n``.

    Se toman los índices únicos: repetir ``{{1}}`` en el mismo texto es válido y no
    añade un parámetro más.
    """
    indices = sorted({int(p) for p in placeholders})
    if indices[0] != 1:
        raise ValueError(
            f"{field}: las variables deben empezar en {{{{1}}}}, "
            f"pero empiezan en {{{{{indices[0]}}}}}"
        )
    expected = list(range(1, len(indices) + 1))
    if indices != expected:
        missing = sorted(set(expected) - set(indices))
        raise ValueError(
            f"{field}: las variables no son consecutivas, falta {{{{{missing[0]}}}}}"
        )
    return len(indices)


def _check_named(placeholders: list[str], *, field: str) -> list[str]:
    """Valida los nombres y devuelve los únicos, en orden de aparición."""
    seen: list[str] = []
    for name in placeholders:
        if not _NAMED_PARAM.match(name):
            raise ValueError(
                f"{field}: {{{{{name}}}}} no es un nombre válido; Meta admite minúsculas, "
                "dígitos y guiones bajos, empezando por letra o guion bajo"
            )
        if name not in seen:
            seen.append(name)
    return seen


def analyze(
    text: str, *, field: str, check_boundaries: bool = False
) -> tuple[ParameterFormat | None, list[str]]:
    """Valida el texto y devuelve ``(formato, variables únicas en orden)``.

    Para el formato posicional las variables se devuelven como ``["1", "2", ...]``, que
    es el orden en que hay que dar los ejemplos.

    ``check_boundaries`` aplica la regla de que el texto no puede empezar ni acabar en
    una variable. Solo se activa para el cuerpo: Meta la enuncia sobre "the message
    template" sin precisar el componente, y aplicarla a la cabecera rechazaría cabeceras
    como ``"Pedido {{1}}"``, que en la práctica Meta aprueba. Ante la ambigüedad, se
    valida donde está documentado el rechazo y se deja pasar lo demás.
    """
    text = text or ""
    _check_unbalanced_braces(text, field=field)

    placeholders = find_placeholders(text)
    if not placeholders:
        return None, []

    if any(not p.strip() for p in placeholders):
        raise ValueError(f"{field}: hay una variable vacía ({{{{}}}})")

    if check_boundaries:
        _check_boundaries(text, field=field)
    fmt = detect_format(text)

    if fmt is ParameterFormat.POSITIONAL:
        count = _check_positional_sequence(placeholders, field=field)
        return fmt, [str(i) for i in range(1, count + 1)]

    return fmt, _check_named(placeholders, field=field)


def require_no_placeholders(text: str, *, field: str) -> None:
    """Falla si el texto tiene variables. El pie de una plantilla no las admite."""
    if find_placeholders(text):
        raise ValueError(f"{field}: no admite variables")
