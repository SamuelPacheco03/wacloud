"""Descarga de medios entrantes desde Meta.

Flujo de la Cloud API: el webhook trae un ``media_id`` → se consulta
``GET /{media_id}`` para obtener una URL temporal → se descargan los bytes de esa
URL (con el token del número). Aquí no se almacena nada: eso lo hace ``ingest``.
"""
from __future__ import annotations

from dataclasses import dataclass

from wacloud.transport import Transport


@dataclass
class DownloadedMedia:
    source_media_id: str | None
    content: bytes
    content_type: str | None
    sha256: str | None = None


async def resolve_media_url(
    transport: Transport,
    media_id: str,
    *,
    access_token: str,
    phone_number_id: str | None = None,
) -> dict:
    """Devuelve la metadata de Meta para ``media_id`` (incluye ``url``, ``mime_type``,
    ``sha256``, ``file_size``)."""
    media_id = (media_id or "").strip()
    if not media_id:
        raise ValueError("media_id es obligatorio")
    return await transport.request(
        "GET",
        f"/{media_id}",
        access_token=access_token,
        phone_number_id=phone_number_id,
    )


async def download_media(
    transport: Transport,
    media_id: str,
    *,
    access_token: str,
    fallback_url: str | None = None,
    phone_number_id: str | None = None,
) -> DownloadedMedia:
    """Resuelve la URL del medio en Meta y descarga sus bytes.

    Si Meta no devuelve URL y se pasó ``fallback_url`` (el que a veces viene en el
    webhook), se usa ese.
    """
    media_id = (media_id or "").strip()
    download_url: str | None = None
    meta_mime: str | None = None
    meta_sha256: str | None = None

    if media_id:
        meta = await resolve_media_url(
            transport, media_id, access_token=access_token, phone_number_id=phone_number_id
        )
        download_url = (meta.get("url") or "").strip() or None
        meta_mime = (meta.get("mime_type") or "").strip() or None
        meta_sha256 = (meta.get("sha256") or "").strip() or None

    if not download_url:
        download_url = (fallback_url or "").strip() or None
    if not download_url:
        raise ValueError("No se pudo resolver la URL de descarga del medio")

    content, detected_mime = await transport.get_bytes(
        download_url, access_token=access_token, phone_number_id=phone_number_id
    )
    return DownloadedMedia(
        source_media_id=media_id or None,
        content=content,
        content_type=meta_mime or detected_mime,
        sha256=meta_sha256,
    )
