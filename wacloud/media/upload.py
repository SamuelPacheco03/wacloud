"""Subida de medios a Meta.

Hay **dos sistemas distintos** y confundirlos es un error frecuente:

1. **Media API** (``POST /{phone_number_id}/media``) devuelve un ``media_id``, que sirve
   para **enviar** mensajes y plantillas. Los medios se retienen 30 días.
2. **Resumable Upload API** (``POST /{app_id}/uploads``) devuelve un ``handle``, que
   sirve para **crear** una plantilla con cabecera de medio.

Un ``media_id`` no vale como ``header_handle`` ni al revés.

Meta recomienda subir el medio una vez y reutilizar el ``media_id`` en vez de mandar
``link`` en cada envío: con URL, Meta tiene que descargar el archivo cada vez, y eso
limita el throughput real.

Referencias:
https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/media
https://developers.facebook.com/docs/graph-api/guides/upload/
"""

from __future__ import annotations

from typing import Any

from wacloud.limits import MediaLimits
from wacloud.transport import Transport

__all__ = [
    "MEDIA_SIZE_LIMITS",
    "delete_media",
    "ensure_within_size_limit",
    "get_media_metadata",
    "upload_media",
    "upload_resumable",
]

#: Tamaño máximo por familia de MIME, en bytes.
#:
#: Corrección habitual: el vídeo son 16 MB, no 100 MB. Los 100 MB son solo para
#: documentos.
MEDIA_SIZE_LIMITS: dict[str, int] = {
    "image": MediaLimits.IMAGE,
    "audio": MediaLimits.AUDIO,
    "video": MediaLimits.VIDEO,
    "application": MediaLimits.DOCUMENT,
    "text": MediaLimits.DOCUMENT,
}


def ensure_within_size_limit(data: bytes, content_type: str) -> None:
    """Comprueba el tamaño antes de gastar ancho de banda y cupo de API.

    Los stickers se tratan aparte: comparten el MIME ``image/webp`` con las imágenes
    normales pero tienen un límite mucho menor (100 KB estáticos, 500 KB animados). Como
    aquí no se puede saber si el webp está animado, se aplica el límite permisivo y se
    deja que Meta rechace el caso concreto.
    """
    family = content_type.split("/", 1)[0].lower()
    limit = MEDIA_SIZE_LIMITS.get(family)
    if limit is None:
        return
    if len(data) > limit:
        raise ValueError(
            f"el archivo pesa {len(data)} bytes y Meta admite como máximo {limit} "
            f"para {content_type}"
        )


async def upload_media(
    transport: Transport,
    *,
    phone_number_id: str,
    access_token: str,
    data: bytes,
    content_type: str,
    filename: str = "upload",
) -> str:
    """Sube un medio y devuelve su ``media_id``.

    El ``media_id`` sirve para enviarlo en mensajes y plantillas durante 30 días.
    """
    if not data:
        raise ValueError("no hay contenido que subir")
    ensure_within_size_limit(data, content_type)

    response = await transport.post_multipart(
        f"/{phone_number_id}/media",
        access_token=access_token,
        files={"file": (filename, data, content_type)},
        data={"messaging_product": "whatsapp", "type": content_type},
        phone_number_id=phone_number_id,
    )
    media_id = response.get("id")
    if not isinstance(media_id, str) or not media_id:
        raise ValueError(f"Meta no devolvió un media_id: {response!r}")
    return media_id


async def get_media_metadata(
    transport: Transport,
    media_id: str,
    *,
    access_token: str,
    phone_number_id: str | None = None,
) -> dict[str, Any]:
    """Metadatos de un medio: ``url``, ``mime_type``, ``sha256`` y ``file_size``.

    La ``url`` que devuelve **caduca a los 5 minutos**. Un 404 al descargar significa
    que caducó: hay que volver a pedir los metadatos, no reintentar la misma URL.
    """
    clean = str(media_id or "").strip()
    if not clean:
        raise ValueError("media_id es obligatorio")
    return await transport.request(
        "GET",
        f"/{clean}",
        access_token=access_token,
        phone_number_id=phone_number_id,
    )


async def delete_media(
    transport: Transport,
    media_id: str,
    *,
    access_token: str,
    phone_number_id: str | None = None,
) -> bool:
    """Borra un medio de los servidores de Meta."""
    clean = str(media_id or "").strip()
    if not clean:
        raise ValueError("media_id es obligatorio")
    response = await transport.request(
        "DELETE",
        f"/{clean}",
        access_token=access_token,
        phone_number_id=phone_number_id,
    )
    return bool(response.get("success", False))


async def upload_resumable(
    transport: Transport,
    *,
    app_id: str,
    access_token: str,
    data: bytes,
    content_type: str,
    file_name: str,
) -> str:
    """Sube un medio por la Resumable Upload API y devuelve su ``handle``.

    Ese handle es lo que espera ``components.media_header`` al crear una plantilla con
    cabecera de imagen, vídeo o documento.

    Tres detalles que separan esto del resto de la Graph API:

    - ``app_id`` es el ID de la **app de Meta**, no el WABA ID ni el phone_number_id.
    - El token debe ser de usuario (un System User con ``whatsapp_business_management``
      funciona), no un app access token.
    - El segundo paso usa ``Authorization: OAuth``, **no ``Bearer``**, y manda el
      contenido como binario crudo sin multipart.

    Se sube en una sola tanda: el protocolo admite reanudar por tramos, pero las
    muestras de cabecera de plantilla son archivos pequeños y partirlas solo añadiría
    modos de fallo.
    """
    if not data:
        raise ValueError("no hay contenido que subir")
    if not str(file_name or "").strip():
        # Meta lo exige y es el parámetro que más se olvida.
        raise ValueError("file_name es obligatorio para crear la sesión de subida")

    session = await transport.request(
        "POST",
        f"/{app_id}/uploads",
        access_token=access_token,
        params={
            "file_name": file_name,
            "file_length": len(data),
            "file_type": content_type,
        },
    )
    session_id = session.get("id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError(f"Meta no devolvió una sesión de subida: {session!r}")

    # ``session_id`` ya viene con el prefijo ``upload:``; es parte del path.
    result = await transport.post_binary(
        f"/{session_id}",
        authorization=f"OAuth {access_token}",
        content=data,
        extra_headers={"file_offset": "0"},
    )
    handle = result.get("h")
    if not isinstance(handle, str) or not handle:
        raise ValueError(f"Meta no devolvió un handle de subida: {result!r}")
    return handle
