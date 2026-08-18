"""Mensajes con un medio adjunto: imagen, documento, vídeo, audio y sticker."""

from __future__ import annotations

from typing import Any

from wacloud.limits import TextLimits, ensure_max_length
from wacloud.recipient import recipient_block

__all__ = [
    "build_audio",
    "build_document",
    "build_image",
    "build_sticker",
    "build_video",
    "media_object",
]


def media_object(
    *,
    link: str | None,
    media_id: str | None,
    caption: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    """Sub-objeto de un medio.

    Meta acepta ``id`` **o** ``link``, nunca ambos. Se prioriza ``media_id`` porque un
    medio ya subido evita que Meta descargue la URL en cada envío, que es lo que Meta
    recomienda para sostener throughput alto.

    Es público (sin guion bajo) porque lo usan varios módulos del paquete: un helper
    compartido no se importa como privado de otro módulo.
    """
    obj: dict[str, Any] = {}
    if media_id and str(media_id).strip():
        obj["id"] = str(media_id).strip()
    elif link and str(link).strip():
        obj["link"] = str(link).strip()
    else:
        raise ValueError("se requiere 'link' o 'media_id'")

    if caption is not None and caption.strip():
        obj["caption"] = ensure_max_length(
            caption.strip(), TextLimits.CAPTION, field="caption"
        )
    if filename is not None and str(filename).strip():
        obj["filename"] = str(filename).strip()
    return obj


def build_image(
    to: str,
    *,
    link: str | None = None,
    media_id: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    """Imagen por URL pública (``link``) o por ``media_id`` ya subido a Meta."""
    return {
        **recipient_block(to),
        "type": "image",
        "image": media_object(link=link, media_id=media_id, caption=caption),
    }


def build_document(
    to: str,
    *,
    link: str | None = None,
    media_id: str | None = None,
    caption: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    """Documento (PDF, Office, etc.). ``filename`` fija el nombre que ve el receptor."""
    return {
        **recipient_block(to),
        "type": "document",
        "document": media_object(
            link=link, media_id=media_id, caption=caption, filename=filename
        ),
    }


def build_video(
    to: str,
    *,
    link: str | None = None,
    media_id: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    """Vídeo por URL pública o ``media_id``. Meta solo acepta H.264 con audio AAC."""
    return {
        **recipient_block(to),
        "type": "video",
        "video": media_object(link=link, media_id=media_id, caption=caption),
    }


def build_audio(
    to: str,
    *,
    link: str | None = None,
    media_id: str | None = None,
) -> dict[str, Any]:
    """Audio por URL pública o ``media_id``. El audio no admite ``caption``."""
    return {
        **recipient_block(to),
        "type": "audio",
        "audio": media_object(link=link, media_id=media_id),
    }


def build_sticker(
    to: str,
    *,
    link: str | None = None,
    media_id: str | None = None,
) -> dict[str, Any]:
    """Sticker por URL pública o ``media_id``. No admite ``caption``.

    Meta solo acepta **WebP**: 100 KB si es estático y 500 KB si es animado. El tamaño no
    se puede validar aquí porque el builder solo ve una referencia, no los bytes; la
    comprobación va al subir (``wacloud.media.upload_media``). Un WebP normal enviado
    como ``image`` sí admite hasta 5 MB: el límite estricto es de los stickers.
    """
    return {
        **recipient_block(to),
        "type": "sticker",
        "sticker": media_object(link=link, media_id=media_id),
    }
