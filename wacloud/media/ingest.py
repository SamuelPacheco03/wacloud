"""Ingesta de medios entrantes: descarga de Meta → StorageBackend del host.

Orquesta ``download_media`` + ``StorageBackend.put`` y devuelve la referencia
almacenada (key) lista para que el host la persista y genere URLs temporales.
"""

from __future__ import annotations

import hashlib
from uuid import uuid4

from wacloud.media.download import download_media
from wacloud.media.storage import StorageBackend, StoredMedia
from wacloud.transport import Transport

# Extensión por mime más comunes en WhatsApp (imagen, audio, video, documento).
_MIME_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/amr": ".amr",
    "audio/aac": ".aac",
    "video/mp4": ".mp4",
    "video/3gpp": ".3gp",
    "application/pdf": ".pdf",
}


def _extension_for(content_type: str | None) -> str:
    if not content_type:
        return ".bin"
    return _MIME_EXTENSION.get(content_type.lower(), ".bin")


def build_media_key(content_type: str | None, *, prefix: str = "whatsapp") -> str:
    """Genera una key única para el objeto en el storage."""
    clean_prefix = prefix.strip("/") or "whatsapp"
    return f"{clean_prefix}/{uuid4().hex}{_extension_for(content_type)}"


async def ingest_inbound_media(
    transport: Transport,
    storage: StorageBackend,
    *,
    media_id: str,
    access_token: str,
    fallback_url: str | None = None,
    key_prefix: str = "whatsapp",
    phone_number_id: str | None = None,
) -> StoredMedia:
    """Descarga el medio desde Meta y lo sube al storage del host.

    Devuelve ``StoredMedia`` (key + content_type + size + sha256). El host guarda
    la key y genera ``presigned_get_url`` cuando necesite servir el archivo.
    """
    downloaded = await download_media(
        transport,
        media_id,
        access_token=access_token,
        fallback_url=fallback_url,
        phone_number_id=phone_number_id,
    )
    content_type = downloaded.content_type or "application/octet-stream"
    key = build_media_key(content_type, prefix=key_prefix)
    stored = await storage.put(key=key, data=downloaded.content, content_type=content_type)

    # Si el backend no calculó sha256, lo completamos aquí (útil para deduplicar).
    if stored.sha256 is None:
        digest = downloaded.sha256 or hashlib.sha256(downloaded.content).hexdigest()
        stored = stored.model_copy(update={"sha256": digest})
    return stored
