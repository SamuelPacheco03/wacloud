"""Tests de descarga e ingesta de medios con MockTransport y un storage fake."""

import hashlib

import httpx

from tests.factories import make_transport
from wacloud.media.ingest import ingest_inbound_media
from wacloud.media.storage import StoredMedia
from wacloud.transport import Transport


class FakeStorage:
    """StorageBackend en memoria para tests."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, *, key: str, data: bytes, content_type: str) -> StoredMedia:
        self.objects[key] = data
        return StoredMedia(key=key, content_type=content_type, size_bytes=len(data))

    async def presigned_get_url(self, *, key: str, ttl_seconds: int) -> str:
        return f"https://r2.example/{key}?exp={ttl_seconds}"


def _transport(handler) -> Transport:
    return make_transport(handler)


async def test_ingest_downloads_and_stores():
    media_bytes = b"\xff\xd8\xff fake-jpeg-bytes"

    def handler(request):
        url = str(request.url)
        # 1) metadata del media_id
        if url.endswith("/MEDIA123"):
            # Sin sha256 en la metadata → ingest calcula el hash de los bytes.
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.fbsbx.com/asset/abc",
                    "mime_type": "image/jpeg",
                },
            )
        # 2) descarga binaria
        if "lookaside.fbsbx.com" in url:
            return httpx.Response(
                200, content=media_bytes, headers={"content-type": "image/jpeg"}
            )
        return httpx.Response(404, json={"error": "not found"})

    storage = FakeStorage()
    stored = await ingest_inbound_media(
        _transport(handler),
        storage,
        media_id="MEDIA123",
        access_token="tok",
        key_prefix="whatsapp/img",
    )

    assert stored.content_type == "image/jpeg"
    assert stored.size_bytes == len(media_bytes)
    assert stored.key.startswith("whatsapp/img/")
    assert stored.key.endswith(".jpg")
    # el contenido quedó en el storage bajo esa key
    assert storage.objects[stored.key] == media_bytes
    # sha256 se completa (el storage fake no lo calcula → lo hace ingest)
    assert stored.sha256 == hashlib.sha256(media_bytes).hexdigest()


async def test_ingest_uses_fallback_url_when_no_media_id_url():
    media_bytes = b"audio-bytes"

    def handler(request):
        url = str(request.url)
        if url.endswith("/AUDIO9"):
            # Meta no devuelve url → se usa fallback_url
            return httpx.Response(200, json={"mime_type": "audio/ogg"})
        if "fallback.example" in url:
            return httpx.Response(
                200, content=media_bytes, headers={"content-type": "audio/ogg"}
            )
        return httpx.Response(404, json={"error": "nope"})

    storage = FakeStorage()
    stored = await ingest_inbound_media(
        _transport(handler),
        storage,
        media_id="AUDIO9",
        access_token="tok",
        fallback_url="https://fallback.example/a.ogg",
    )
    assert stored.key.endswith(".ogg")
    assert storage.objects[stored.key] == media_bytes


async def test_fake_storage_satisfies_protocol():
    # FakeStorage cumple el Protocolo StorageBackend en runtime.
    from wacloud.media.storage import StorageBackend

    assert isinstance(FakeStorage(), StorageBackend)
