"""Tests de subida de medios: Media API y Resumable Upload API."""

import httpx
import pytest

from tests.factories import make_transport
from wacloud.media.upload import (
    delete_media,
    ensure_within_size_limit,
    get_media_metadata,
    upload_media,
    upload_resumable,
)

# --- Límites de tamaño -------------------------------------------------------


def test_video_limit_is_16mb_not_100mb():
    """Corrección frecuente: los 100 MB son solo para documentos."""
    ensure_within_size_limit(b"x" * (16 * 1024 * 1024), "video/mp4")
    with pytest.raises(ValueError, match="16777216"):
        ensure_within_size_limit(b"x" * (16 * 1024 * 1024 + 1), "video/mp4")


def test_image_limit_is_5mb():
    with pytest.raises(ValueError, match="5242880"):
        ensure_within_size_limit(b"x" * (5 * 1024 * 1024 + 1), "image/jpeg")


def test_documents_allow_100mb():
    ensure_within_size_limit(b"x" * (50 * 1024 * 1024), "application/pdf")


def test_unknown_family_is_not_blocked():
    """Ante un MIME desconocido se deja pasar y decide Meta."""
    ensure_within_size_limit(b"x" * 999, "cosa/rara")


# --- Media API ---------------------------------------------------------------


async def test_upload_media_posts_multipart_and_returns_id():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["content_type"] = request.headers["content-type"]
        captured["body"] = request.content
        return httpx.Response(200, json={"id": "1013859600285441"})

    transport = make_transport(handler)
    media_id = await upload_media(
        transport,
        phone_number_id="PNID",
        access_token="tok",
        data=b"binario",
        content_type="image/jpeg",
        filename="foto.jpg",
    )

    assert media_id == "1013859600285441"
    assert captured["url"].endswith("/PNID/media")
    assert captured["content_type"].startswith("multipart/form-data")
    assert b"whatsapp" in captured["body"]
    assert b"binario" in captured["body"]


async def test_upload_media_validates_size_before_the_request():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"id": "x"})

    transport = make_transport(handler)
    with pytest.raises(ValueError, match="como máximo"):
        await upload_media(
            transport,
            phone_number_id="PNID",
            access_token="tok",
            data=b"x" * (6 * 1024 * 1024),
            content_type="image/jpeg",
        )
    assert calls["n"] == 0, "no debe gastarse una llamada en algo que ya sabemos que falla"


async def test_upload_media_rejects_empty_content():
    transport = make_transport(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="no hay contenido"):
        await upload_media(
            transport,
            phone_number_id="PNID",
            access_token="tok",
            data=b"",
            content_type="image/jpeg",
        )


async def test_upload_media_fails_loudly_without_id():
    transport = make_transport(lambda r: httpx.Response(200, json={"ok": True}))
    with pytest.raises(ValueError, match="no devolvió un media_id"):
        await upload_media(
            transport,
            phone_number_id="PNID",
            access_token="tok",
            data=b"x",
            content_type="image/jpeg",
        )


async def test_get_media_metadata_returns_url_and_mime():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "url": "https://lookaside.fbsbx.com/x",
                "mime_type": "image/jpeg",
                "sha256": "29ac2b",
                "file_size": "2400",
            },
        )

    meta = await get_media_metadata(make_transport(handler), "MID", access_token="tok")
    assert meta["mime_type"] == "image/jpeg"


async def test_delete_media_reports_success():
    transport = make_transport(lambda r: httpx.Response(200, json={"success": True}))
    assert await delete_media(transport, "MID", access_token="tok") is True


# --- Resumable Upload API ----------------------------------------------------


async def test_resumable_upload_runs_two_steps_and_returns_handle():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"id": "upload:MTphdHRhY2"})
        return httpx.Response(200, json={"h": "4::aW1hZ2UvanBlZw==:ARZ"})

    handle = await upload_resumable(
        make_transport(handler),
        app_id="APPID",
        access_token="tok",
        data=b"bytes-de-imagen",
        content_type="image/jpeg",
        file_name="muestra.jpg",
    )

    assert handle == "4::aW1hZ2UvanBlZw==:ARZ"
    assert len(calls) == 2


async def test_resumable_session_sends_required_params():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"id": "upload:SID"})
        return httpx.Response(200, json={"h": "handle"})

    await upload_resumable(
        make_transport(handler),
        app_id="APPID",
        access_token="tok",
        data=b"1234567890",
        content_type="image/png",
        file_name="muestra.png",
    )

    params = calls[0].url.params
    assert calls[0].url.path.endswith("/APPID/uploads")
    assert params["file_name"] == "muestra.png"
    assert params["file_length"] == "10"
    assert params["file_type"] == "image/png"


async def test_resumable_second_step_uses_oauth_scheme_not_bearer():
    """Este endpoint es la excepción: usa ``OAuth``, no ``Bearer``."""
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"id": "upload:SID"})
        return httpx.Response(200, json={"h": "handle"})

    await upload_resumable(
        make_transport(handler),
        app_id="APPID",
        access_token="tok",
        data=b"contenido",
        content_type="image/jpeg",
        file_name="x.jpg",
    )

    upload = calls[1]
    assert upload.headers["Authorization"] == "OAuth tok"
    assert upload.headers["file_offset"] == "0"
    assert upload.content == b"contenido", "el cuerpo va crudo, sin multipart"
    assert upload.url.path.endswith("/upload:SID")


async def test_resumable_requires_file_name():
    """Meta lo exige y es el parámetro que más se olvida."""
    transport = make_transport(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="file_name es obligatorio"):
        await upload_resumable(
            transport,
            app_id="APPID",
            access_token="tok",
            data=b"x",
            content_type="image/jpeg",
            file_name="",
        )


async def test_resumable_fails_loudly_without_handle():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"id": "upload:SID"})
        return httpx.Response(200, json={"ok": True})

    with pytest.raises(ValueError, match="no devolvió un handle"):
        await upload_resumable(
            make_transport(handler),
            app_id="APPID",
            access_token="tok",
            data=b"x",
            content_type="image/jpeg",
            file_name="x.jpg",
        )
