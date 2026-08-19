"""Parámetros para **enviar** una plantilla ya aprobada.

Meta llama "components" tanto a la definición de la plantilla como a los valores que se
mandan al enviarla, pero son estructuras distintas: la definición lleva ``example``, el
envío lleva ``parameters``. Aquí está la segunda; la primera, en
``wacloud.templates.components``.

Dos detalles donde la documentación de Meta se contradice a sí misma y que aquí se
resuelven siempre igual:

- ``index`` va como **cadena** (``"0"``), no como entero. Solo la página de cupones lo
  muestra como número.
- ``sub_type`` va en **minúscula**. Solo la página de catálogo lo muestra en mayúscula.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/templates
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "body",
    "button_catalog",
    "button_copy_code",
    "button_flow",
    "button_mpm",
    "button_quick_reply",
    "button_url",
    "currency",
    "date_time",
    "document",
    "header",
    "image",
    "location",
    "text",
    "video",
]

#: Meta admite como mucho 10 botones, indexados de "0" a "9".
_MAX_BUTTON_INDEX = 9


def text(value: str, *, name: str | None = None) -> dict[str, Any]:
    """Parámetro de texto.

    ``name`` solo se pasa en plantillas con ``parameter_format=NAMED``; en las
    posicionales lo que manda es el orden dentro de la lista.
    """
    param: dict[str, Any] = {"type": "text", "text": str(value)}
    if name:
        param["parameter_name"] = name
    return param


def currency(
    *, fallback_value: str, code: str, amount_1000: int, name: str | None = None
) -> dict[str, Any]:
    """Parámetro de moneda.

    ``amount_1000`` es el importe multiplicado por 1000 y en entero: 100,99 € se manda
    como ``100990``. ``fallback_value`` es lo que se muestra si el cliente no sabe
    formatear la moneda, así que debe ser legible tal cual.
    """
    param: dict[str, Any] = {
        "type": "currency",
        "currency": {
            "fallback_value": fallback_value,
            "code": code,
            "amount_1000": int(amount_1000),
        },
    }
    if name:
        param["parameter_name"] = name
    return param


def date_time(fallback_value: str, *, name: str | None = None) -> dict[str, Any]:
    """Parámetro de fecha y hora.

    Meta define campos desglosados (``day_of_month``, ``month``, ``year``…) pero en la
    práctica solo honra ``fallback_value``, así que es lo único que se manda: enviar el
    desglose da una falsa sensación de localización que no ocurre.
    """
    param: dict[str, Any] = {
        "type": "date_time",
        "date_time": {"fallback_value": fallback_value},
    }
    if name:
        param["parameter_name"] = name
    return param


def _media_param(
    kind: str,
    *,
    link: str | None,
    media_id: str | None,
    filename: str | None = None,
) -> dict[str, Any]:
    """Parámetro de medio para la cabecera. Meta acepta ``id`` **o** ``link``."""
    obj: dict[str, Any] = {}
    if media_id and str(media_id).strip():
        obj["id"] = str(media_id).strip()
    elif link and str(link).strip():
        obj["link"] = str(link).strip()
    else:
        raise ValueError(f"{kind}: se requiere 'link' o 'media_id'")
    if filename:
        obj["filename"] = str(filename).strip()
    return {"type": kind, kind: obj}


def image(*, link: str | None = None, media_id: str | None = None) -> dict[str, Any]:
    """Imagen para una cabecera de plantilla con formato ``IMAGE``."""
    return _media_param("image", link=link, media_id=media_id)


def video(*, link: str | None = None, media_id: str | None = None) -> dict[str, Any]:
    """Vídeo para una cabecera de plantilla con formato ``VIDEO``."""
    return _media_param("video", link=link, media_id=media_id)


def document(
    *,
    link: str | None = None,
    media_id: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    """Documento para una cabecera de plantilla con formato ``DOCUMENT``."""
    return _media_param("document", link=link, media_id=media_id, filename=filename)


def location(
    *, latitude: str, longitude: str, name: str = "", address: str = ""
) -> dict[str, Any]:
    """Ubicación para una cabecera de plantilla con formato ``LOCATION``."""
    return {
        "type": "location",
        "location": {
            "latitude": str(latitude),
            "longitude": str(longitude),
            "name": name,
            "address": address,
        },
    }


# -- Agrupación en componentes de envío -------------------------------------------


def header(parameters: list[dict[str, Any]]) -> dict[str, Any]:
    """Componente de cabecera con sus parámetros."""
    return {"type": "header", "parameters": list(parameters)}


def body(parameters: list[dict[str, Any]]) -> dict[str, Any]:
    """Componente de cuerpo con sus parámetros."""
    return {"type": "body", "parameters": list(parameters)}


def _button(sub_type: str, index: int, parameters: list[dict[str, Any]]) -> dict[str, Any]:
    if not 0 <= index <= _MAX_BUTTON_INDEX:
        raise ValueError(
            f"el índice del botón debe estar entre 0 y {_MAX_BUTTON_INDEX}, no {index}"
        )
    return {
        "type": "button",
        "sub_type": sub_type,
        "index": str(index),
        "parameters": parameters,
    }


def button_url(index: int, value: str) -> dict[str, Any]:
    """Sufijo variable de un botón URL.

    El valor se inserta donde la plantilla tiene ``{{1}}``. Debe ir **percent-encoded**:
    Meta no lo escapa, así que un valor con acentos o espacios rompe el enlace.
    """
    return _button("url", index, [{"type": "text", "text": str(value)}])


def button_quick_reply(index: int, payload: str) -> dict[str, Any]:
    """Dato que se devuelve por webhook cuando el usuario pulsa la respuesta rápida."""
    return _button("quick_reply", index, [{"type": "payload", "payload": str(payload)}])


def button_copy_code(index: int, code: str) -> dict[str, Any]:
    """Código que copia al portapapeles un botón ``COPY_CODE``."""
    return _button("copy_code", index, [{"type": "coupon_code", "coupon_code": str(code)}])


def button_flow(
    index: int,
    *,
    flow_token: str,
    flow_action_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Datos de arranque de un botón de Flow.

    ``flow_token`` es la referencia con la que se correlaciona la respuesta: Meta avisa
    de que *"the Flow response does not include the Flow ID"*, así que conviene meter
    aquí un identificador propio.
    """
    action: dict[str, Any] = {"flow_token": flow_token}
    if flow_action_data:
        action["flow_action_data"] = flow_action_data
    return _button("flow", index, [{"type": "action", "action": action}])


def button_catalog(index: int, thumbnail_product_retailer_id: str) -> dict[str, Any]:
    """Producto que se usa como miniatura de un botón de catálogo."""
    return _button(
        "catalog",
        index,
        [
            {
                "type": "action",
                "action": {"thumbnail_product_retailer_id": thumbnail_product_retailer_id},
            }
        ],
    )


def button_mpm(
    index: int,
    *,
    thumbnail_product_retailer_id: str,
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Secciones de productos de un botón multi-producto."""
    return _button(
        "mpm",
        index,
        [
            {
                "type": "action",
                "action": {
                    "thumbnail_product_retailer_id": thumbnail_product_retailer_id,
                    "sections": sections,
                },
            }
        ],
    )
