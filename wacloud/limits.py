"""Límites documentados por Meta para la Cloud API.

Se centralizan aquí para que no aparezcan como números mágicos repartidos por los
builders, y para dejar constancia de la fuente. Meta los aplica del lado servidor: el
valor de validarlos aquí es fallar con un mensaje útil en vez de gastar cupo de API
para recibir un ``400`` genérico.

Cuando la documentación de Meta se contradice entre páginas se elige el valor **más
restrictivo**, que es el seguro. Los casos concretos están anotados.
"""

from __future__ import annotations


class TextLimits:
    """Mensajes de texto y pies de foto."""

    #: Cuerpo de un mensaje ``type=text``.
    BODY = 4096
    #: Pie de imagen, vídeo o documento.
    CAPTION = 1024


class InteractiveLimits:
    """Mensajes interactivos (botones, listas, CTA).

    Meta documenta ``body.text`` como 4096 en la página de listas y como 1024 en las de
    botones, CTA, ubicación y producto. Se toma **1024** como techo universal seguro.
    """

    BODY = 1024
    FOOTER = 60
    HEADER_TEXT = 60

    #: Botones de respuesta rápida.
    MAX_REPLY_BUTTONS = 3
    REPLY_BUTTON_TITLE = 20
    REPLY_BUTTON_ID = 256

    #: Botón CTA que abre una URL.
    CTA_DISPLAY_TEXT = 20

    #: Etiqueta del botón que abre un Flow. Meta no publica un tope duro; 30 es el
    #: valor que recomienda y que respetan sus ejemplos.
    FLOW_CTA = 30

    #: Listas. El límite de filas es **total entre todas las secciones**, no por sección.
    MAX_LIST_SECTIONS = 10
    MAX_LIST_ROWS_TOTAL = 10
    LIST_BUTTON = 20
    LIST_SECTION_TITLE = 24
    LIST_ROW_TITLE = 24
    LIST_ROW_DESCRIPTION = 72
    LIST_ROW_ID = 200


class TemplateLimits:
    """Creación y envío de plantillas."""

    NAME = 512
    #: Header de texto: un solo parámetro permitido.
    HEADER_TEXT = 60
    HEADER_TEXT_MAX_VARIABLES = 1
    BODY = 1024
    #: El pie de una plantilla no admite variables.
    FOOTER = 60

    BUTTON_TEXT = 25
    #: Los botones de Flow y de llamada de voz usan un tope menor.
    FLOW_BUTTON_TEXT = 20
    VOICE_CALL_BUTTON_TEXT = 20

    URL = 2000
    PHONE_NUMBER = 20
    COPY_CODE_EXAMPLE = 20

    MAX_BUTTONS = 10
    MAX_URL_BUTTONS = 2
    MAX_PHONE_NUMBER_BUTTONS = 1
    MAX_COPY_CODE_BUTTONS = 1
    MAX_QUICK_REPLY_BUTTONS = 10

    #: Rango que acepta Meta para la caducidad del código en plantillas de autenticación.
    OTP_EXPIRATION_MINUTES = (1, 90)


class MediaLimits:
    """Tamaños máximos por categoría, en bytes.

    Corrección frecuente: el vídeo son **16 MB**, no 100 MB. Los 100 MB aplican solo a
    documentos y son además el techo absoluto de la plataforma.
    """

    IMAGE = 5 * 1024 * 1024
    AUDIO = 16 * 1024 * 1024
    VIDEO = 16 * 1024 * 1024
    DOCUMENT = 100 * 1024 * 1024
    STICKER_STATIC = 100 * 1024
    STICKER_ANIMATED = 500 * 1024


def ensure_max_length(value: str, maximum: int, *, field: str) -> str:
    """Valida la longitud de un campo y lo devuelve intacto.

    Se valida en vez de recortar: truncar en silencio hace que el usuario final reciba
    un mensaje distinto del que el host creyó enviar, y ese fallo es invisible.
    """
    if len(value) > maximum:
        raise ValueError(
            f"{field} excede el límite de Meta: {len(value)} caracteres, máximo {maximum}"
        )
    return value


def ensure_max_items(items: list[object], maximum: int, *, field: str) -> None:
    """Valida el número de elementos de una colección."""
    if len(items) > maximum:
        raise ValueError(
            f"{field} excede el límite de Meta: {len(items)} elementos, máximo {maximum}"
        )
