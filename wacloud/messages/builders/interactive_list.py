"""Mensajes interactivos de lista.

Muestra un botón que abre un menú con opciones agrupadas en secciones.

El límite que más se malinterpreta: **10 filas en total entre todas las secciones**, no
10 por sección. Con 10 secciones no caben 100 opciones; caben 10 repartidas como se
quiera. Meta lo dice literalmente: *"up to 10 sections, with up to 10 rows across all
sections combined"*.

Otra restricción fácil de pasar por alto: la cabecera de una lista **solo admite texto**,
a diferencia de la de los botones de respuesta, que acepta imagen, vídeo o documento.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/interactive
"""

from __future__ import annotations

from typing import Any

from wacloud.limits import InteractiveLimits, ensure_max_items, ensure_max_length
from wacloud.messages.builders.interactive import interactive_message

__all__ = ["build_interactive_list", "list_row", "list_section"]


def list_row(row_id: str, title: str, *, description: str | None = None) -> dict[str, Any]:
    """Una opción del menú.

    ``row_id`` es lo que llega por webhook cuando el usuario la elige, así que conviene
    que sea un identificador estable y no el texto visible.
    """
    clean_id = str(row_id or "").strip()
    if not clean_id:
        raise ValueError("el id de la fila es obligatorio")
    clean_title = str(title or "").strip()
    if not clean_title:
        raise ValueError("el título de la fila es obligatorio")

    row: dict[str, Any] = {
        "id": ensure_max_length(clean_id, InteractiveLimits.LIST_ROW_ID, field="row.id"),
        "title": ensure_max_length(
            clean_title, InteractiveLimits.LIST_ROW_TITLE, field="row.title"
        ),
    }
    if description is not None and str(description).strip():
        row["description"] = ensure_max_length(
            str(description).strip(),
            InteractiveLimits.LIST_ROW_DESCRIPTION,
            field="row.description",
        )
    return row


def list_section(rows: list[dict[str, Any]], *, title: str | None = None) -> dict[str, Any]:
    """Agrupa filas bajo un encabezado.

    ``title`` es opcional con una sola sección y **obligatorio** en cuanto hay más de una;
    esa comprobación la hace ``build_interactive_list``, que es quien ve el conjunto.
    """
    if not rows:
        raise ValueError("la sección necesita al menos una fila")
    section: dict[str, Any] = {"rows": list(rows)}
    if title is not None and str(title).strip():
        section["title"] = ensure_max_length(
            str(title).strip(),
            InteractiveLimits.LIST_SECTION_TITLE,
            field="section.title",
        )
    return section


def _check_total_rows(sections: list[dict[str, Any]]) -> None:
    """Valida el tope global de filas, que es el error más común con las listas."""
    total = sum(len(section.get("rows", [])) for section in sections)
    if total > InteractiveLimits.MAX_LIST_ROWS_TOTAL:
        raise ValueError(
            f"una lista admite {InteractiveLimits.MAX_LIST_ROWS_TOTAL} filas en total "
            f"entre todas las secciones, se dieron {total}"
        )


def _check_unique_row_ids(sections: list[dict[str, Any]]) -> None:
    """Dos filas con el mismo id harían indistinguible la respuesta del usuario."""
    seen: set[str] = set()
    for section in sections:
        for row in section.get("rows", []):
            row_id = row.get("id")
            if row_id in seen:
                raise ValueError(f"el id de fila {row_id!r} está repetido")
            seen.add(row_id)


def build_interactive_list(
    to: str,
    body: str,
    button: str,
    sections: list[dict[str, Any]],
    *,
    header: str | None = None,
    footer: str | None = None,
) -> dict[str, Any]:
    """Mensaje con un menú de opciones.

    ``button`` es la etiqueta que abre el menú (máximo 20 caracteres). ``header`` es una
    cadena, no un objeto: la lista es el único interactivo cuya cabecera solo admite
    texto.
    """
    if not sections:
        raise ValueError("se requiere al menos una sección")
    ensure_max_items(
        list(sections), InteractiveLimits.MAX_LIST_SECTIONS, field="action.sections"
    )
    _check_total_rows(sections)
    _check_unique_row_ids(sections)

    if len(sections) > 1 and any("title" not in s for s in sections):
        raise ValueError("con más de una sección, todas necesitan 'title'")

    clean_button = str(button or "").strip()
    if not clean_button:
        raise ValueError("la etiqueta del botón es obligatoria")
    ensure_max_length(clean_button, InteractiveLimits.LIST_BUTTON, field="action.button")
    ensure_max_length(body, InteractiveLimits.BODY, field="interactive.body")

    interactive: dict[str, Any] = {
        "type": "list",
        "body": {"text": body},
        "action": {"button": clean_button, "sections": list(sections)},
    }

    header_object = None
    if header is not None and str(header).strip():
        header_object = {
            "type": "text",
            "text": ensure_max_length(
                str(header).strip(),
                InteractiveLimits.HEADER_TEXT,
                field="interactive.header",
            ),
        }

    return interactive_message(to, interactive, header=header_object, footer=footer)
