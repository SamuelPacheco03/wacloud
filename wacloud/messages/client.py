"""Cliente de alto nivel para enviar mensajes por la Graph API.

``MessagesClient`` une el ``Transport`` (red + reintentos) con el
``CredentialResolver`` (token por número, inyectado por el host). Resuelve las
credenciales por ``phone_number_id`` y delega el POST al transporte.

El envío batch es **secuencial y preserva el orden**: Meta no expone un endpoint
batch real, así que mandamos los mensajes uno a uno (resolviendo el token una
sola vez) y devolvemos un ``BatchSendResult`` por posición. Un fallo en un
mensaje no aborta el resto: queda registrado en su posición y se continúa.
"""
from __future__ import annotations

from typing import Any

from wacloud.config import DEFAULT_CONFIG, GraphConfig
from wacloud.credentials import CredentialResolver
from wacloud.errors import WaCloudError
from wacloud.messages import builders
from wacloud.models import BatchSendResult, SendResult
from wacloud.transport import Transport


class MessagesClient:
    def __init__(
        self,
        transport: Transport,
        resolver: CredentialResolver,
        *,
        config: GraphConfig | None = None,
    ) -> None:
        self._transport = transport
        self._resolver = resolver
        self._config = config or DEFAULT_CONFIG

    async def send_payload(
        self, payload: dict[str, Any], *, phone_number_id: str
    ) -> SendResult:
        """Envía un payload ya construido (ver ``builders``) al número emisor."""
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        body = await self._transport.request(
            "POST",
            f"/{phone_number_id}/messages",
            access_token=credentials.access_token,
            json=payload,
            phone_number_id=phone_number_id,
        )
        return SendResult.from_response(body)

    async def send_text(
        self, to: str, body: str, *, phone_number_id: str, preview_url: bool = False
    ) -> SendResult:
        return await self.send_payload(
            builders.build_text(to, body, preview_url=preview_url),
            phone_number_id=phone_number_id,
        )

    async def send_image(
        self,
        to: str,
        *,
        phone_number_id: str,
        link: str | None = None,
        media_id: str | None = None,
        caption: str | None = None,
    ) -> SendResult:
        return await self.send_payload(
            builders.build_image(to, link=link, media_id=media_id, caption=caption),
            phone_number_id=phone_number_id,
        )

    async def send_document(
        self,
        to: str,
        *,
        phone_number_id: str,
        link: str | None = None,
        media_id: str | None = None,
        caption: str | None = None,
        filename: str | None = None,
    ) -> SendResult:
        return await self.send_payload(
            builders.build_document(
                to, link=link, media_id=media_id, caption=caption, filename=filename
            ),
            phone_number_id=phone_number_id,
        )

    async def send_video(
        self,
        to: str,
        *,
        phone_number_id: str,
        link: str | None = None,
        media_id: str | None = None,
        caption: str | None = None,
    ) -> SendResult:
        return await self.send_payload(
            builders.build_video(to, link=link, media_id=media_id, caption=caption),
            phone_number_id=phone_number_id,
        )

    async def send_audio(
        self,
        to: str,
        *,
        phone_number_id: str,
        link: str | None = None,
        media_id: str | None = None,
    ) -> SendResult:
        return await self.send_payload(
            builders.build_audio(to, link=link, media_id=media_id),
            phone_number_id=phone_number_id,
        )

    async def send_template(
        self,
        to: str,
        name: str,
        language_code: str,
        components: list[dict[str, Any]] | None = None,
        *,
        phone_number_id: str,
    ) -> SendResult:
        """Envía una plantilla ya aprobada (``/messages``). Para marketing usar
        ``TemplatesClient.send_marketing``."""
        return await self.send_payload(
            builders.build_template(to, name, language_code, components),
            phone_number_id=phone_number_id,
        )

    async def send_batch(
        self, payloads: list[dict[str, Any]], *, phone_number_id: str
    ) -> list[BatchSendResult]:
        """Envía varios payloads al mismo número, en orden, resolviendo el token
        una sola vez. Devuelve un resultado por posición."""
        if not payloads:
            return []
        # Resolver una vez: si el host no encuentra credenciales, todo el lote
        # falla con el mismo motivo (no tiene sentido reintentar por mensaje).
        try:
            credentials = await self._resolver.for_phone_number_id(phone_number_id)
        except WaCloudError as exc:
            return [BatchSendResult.failed(str(exc)) for _ in payloads]

        results: list[BatchSendResult] = []
        for payload in payloads:
            try:
                body = await self._transport.request(
                    "POST",
                    f"/{phone_number_id}/messages",
                    access_token=credentials.access_token,
                    json=payload,
                    phone_number_id=phone_number_id,
                )
                results.append(BatchSendResult.accepted(body))
            except WaCloudError as exc:
                results.append(BatchSendResult.failed(str(exc)))
        return results

    async def mark_read(
        self,
        *,
        phone_number_id: str,
        message_id: str,
        typing: bool = True,
        typing_type: str = "text",
    ) -> dict[str, Any]:
        """Marca un mensaje entrante como leído y (por defecto) muestra el
        indicador de escritura."""
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        payload = builders.build_mark_read(
            message_id, typing=typing, typing_type=typing_type
        )
        return await self._transport.request(
            "POST",
            f"/{phone_number_id}/messages",
            access_token=credentials.access_token,
            json=payload,
            phone_number_id=phone_number_id,
        )
