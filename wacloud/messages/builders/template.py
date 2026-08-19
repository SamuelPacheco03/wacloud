"""Envío de plantillas ya aprobadas."""

from __future__ import annotations

from typing import Any

from wacloud.recipient import recipient_block

__all__ = ["build_template"]


def build_template(
    to: str,
    name: str,
    language_code: str,
    components: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Envío de una plantilla ya aprobada (``type=template``).

    ``components`` va en el formato de Meta: una entrada por ``header``/``body``/
    ``button``, cada una con sus ``parameters``. Se construyen con
    ``wacloud.templates.parameters``.
    """
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("el nombre de la plantilla es obligatorio")
    return {
        **recipient_block(to),
        "type": "template",
        "template": {
            "name": clean_name,
            "language": {"code": str(language_code or "es").strip()},
            "components": components or [],
        },
    }
