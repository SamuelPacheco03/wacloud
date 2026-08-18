"""Cliente de alto nivel para enviar mensajes por la Graph API.

``MessagesClient`` une el ``Transport`` (red y reintentos) con el ``CredentialResolver``
(token por número, inyectado por el host). Su única responsabilidad es orquestar:
resolver credenciales y delegar. Los payloads los arman los ``builders``.

El envío en lote es **secuencial y preserva el orden**: Meta no expone un endpoint batch
real. Se resuelve el token una sola vez y se devuelve un ``BatchSendResult`` por
posición; un fallo individual no aborta el resto.

Aviso sobre el lote: Meta limita a **1 mensaje cada 6 segundos al mismo destinatario**
(código ``131056``). Un lote dirigido a un único usuario debe ir espaciado por el host,
o mediante el ``rate_limit_hook`` del transporte.
"""

from __future__ import annotations

from typing import Any

from wacloud.credentials import CredentialResolver
from wacloud.errors import WaCloudError
from wacloud.messages import builders
from wacloud.models import BatchSendResult, SendResult
from wacloud.transport import Transport


class MessagesClient:
    def __init__(self, transport: Transport, resolver: CredentialResolver) -> None:
        self._transport = transport
        self._resolver = resolver

    # -- Envío base --------------------------------------------------------------

    async def _post_message(
        self, payload: dict[str, Any], *, phone_number_id: str, access_token: str
    ) -> dict[str, Any]:
        """POST a ``/{phone_number_id}/messages`` con un token ya resuelto.

        Existe para que el envío individual y el lote compartan exactamente la misma
        llamada: el lote resuelve el token una vez y lo reutiliza.
        """
        return await self._transport.request(
            "POST",
            f"/{phone_number_id}/messages",
            access_token=access_token,
            json=payload,
            phone_number_id=phone_number_id,
        )

    async def send_payload(
        self,
        payload: dict[str, Any],
        *,
        phone_number_id: str,
        reply_to: str | None = None,
    ) -> SendResult:
        """Envía un payload ya construido (ver ``builders``) desde el número emisor.

        ``reply_to`` es el ``wamid`` del mensaje que se cita. Funciona con cualquier tipo
        de mensaje, así que está aquí y no repetido en cada builder.
        """
        if reply_to:
            payload = builders.as_reply(payload, reply_to)
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        body = await self._post_message(
            payload,
            phone_number_id=phone_number_id,
            access_token=credentials.access_token,
        )
        return SendResult.from_response(body)

    async def send_batch(
        self, payloads: list[dict[str, Any]], *, phone_number_id: str
    ) -> list[BatchSendResult]:
        """Envía varios payloads en orden, resolviendo el token una sola vez.

        Devuelve un resultado por posición de entrada. Si las credenciales no se pueden
        resolver, todo el lote falla con el mismo motivo: reintentar por mensaje no
        cambiaría nada.
        """
        if not payloads:
            return []

        try:
            credentials = await self._resolver.for_phone_number_id(phone_number_id)
        except WaCloudError as exc:
            return [BatchSendResult.failed(str(exc)) for _ in payloads]

        results: list[BatchSendResult] = []
        for payload in payloads:
            try:
                body = await self._post_message(
                    payload,
                    phone_number_id=phone_number_id,
                    access_token=credentials.access_token,
                )
                results.append(BatchSendResult.accepted(body))
            except WaCloudError as exc:
                results.append(BatchSendResult.failed(str(exc), code=exc.code))
        return results

    # -- Atajos por tipo de mensaje ----------------------------------------------

    async def send_text(
        self,
        to: str,
        body: str,
        *,
        phone_number_id: str,
        preview_url: bool = False,
        reply_to: str | None = None,
    ) -> SendResult:
        return await self.send_payload(
            builders.build_text(to, body, preview_url=preview_url),
            phone_number_id=phone_number_id,
            reply_to=reply_to,
        )

    async def send_image(
        self,
        to: str,
        *,
        phone_number_id: str,
        link: str | None = None,
        media_id: str | None = None,
        caption: str | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        return await self.send_payload(
            builders.build_image(to, link=link, media_id=media_id, caption=caption),
            phone_number_id=phone_number_id,
            reply_to=reply_to,
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
        reply_to: str | None = None,
    ) -> SendResult:
        return await self.send_payload(
            builders.build_document(
                to, link=link, media_id=media_id, caption=caption, filename=filename
            ),
            phone_number_id=phone_number_id,
            reply_to=reply_to,
        )

    async def send_video(
        self,
        to: str,
        *,
        phone_number_id: str,
        link: str | None = None,
        media_id: str | None = None,
        caption: str | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        return await self.send_payload(
            builders.build_video(to, link=link, media_id=media_id, caption=caption),
            phone_number_id=phone_number_id,
            reply_to=reply_to,
        )

    async def send_audio(
        self,
        to: str,
        *,
        phone_number_id: str,
        link: str | None = None,
        media_id: str | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        return await self.send_payload(
            builders.build_audio(to, link=link, media_id=media_id),
            phone_number_id=phone_number_id,
            reply_to=reply_to,
        )

    async def send_list(
        self,
        to: str,
        body: str,
        button: str,
        sections: list[dict[str, Any]],
        *,
        phone_number_id: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        """Envía un menú de opciones.

        Las secciones se construyen con ``builders.list_section`` y ``builders.list_row``.
        Recuerda el tope: 10 filas **en total** entre todas las secciones.
        """
        return await self.send_payload(
            builders.build_interactive_list(
                to, body, button, sections, header=header, footer=footer
            ),
            phone_number_id=phone_number_id,
            reply_to=reply_to,
        )

    async def send_flow(
        self,
        to: str,
        body: str,
        cta: str,
        *,
        phone_number_id: str,
        flow_token: str,
        flow_id: str | None = None,
        flow_name: str | None = None,
        screen: str | None = None,
        data: dict[str, Any] | None = None,
        header: dict[str, Any] | None = None,
        footer: str | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        """Envía un mensaje que abre un WhatsApp Flow.

        ``flow_token`` viaja de vuelta en la respuesta y es lo único que permite
        correlacionarla: Meta no incluye el ``flow_id`` en el envío recibido.
        """
        return await self.send_payload(
            builders.build_interactive_flow(
                to,
                body,
                cta,
                flow_token=flow_token,
                flow_id=flow_id,
                flow_name=flow_name,
                screen=screen,
                data=data,
                header=header,
                footer=footer,
            ),
            phone_number_id=phone_number_id,
            reply_to=reply_to,
        )

    async def send_sticker(
        self,
        to: str,
        *,
        phone_number_id: str,
        link: str | None = None,
        media_id: str | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        """Envía un sticker. Meta solo acepta WebP (100 KB estático, 500 KB animado)."""
        return await self.send_payload(
            builders.build_sticker(to, link=link, media_id=media_id),
            phone_number_id=phone_number_id,
            reply_to=reply_to,
        )

    async def send_location(
        self,
        to: str,
        *,
        phone_number_id: str,
        latitude: float | str,
        longitude: float | str,
        name: str | None = None,
        address: str | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        """Comparte una ubicación en el mapa."""
        return await self.send_payload(
            builders.build_location(
                to,
                latitude=latitude,
                longitude=longitude,
                name=name,
                address=address,
            ),
            phone_number_id=phone_number_id,
            reply_to=reply_to,
        )

    async def send_contacts(
        self,
        to: str,
        contacts: list[dict[str, Any]],
        *,
        phone_number_id: str,
        reply_to: str | None = None,
    ) -> SendResult:
        """Envía una o varias tarjetas de contacto.

        Los contactos se construyen con ``builders.contact`` y sus piezas
        (``contact_name``, ``contact_phone``…).
        """
        return await self.send_payload(
            builders.build_contacts(to, contacts),
            phone_number_id=phone_number_id,
            reply_to=reply_to,
        )

    async def send_reaction(
        self, to: str, *, phone_number_id: str, message_id: str, emoji: str
    ) -> SendResult:
        """Reacciona con un emoji a un mensaje recibido.

        No admite ``reply_to``: una reacción ya apunta a un mensaje concreto.
        """
        return await self.send_payload(
            builders.build_reaction(to, message_id, emoji),
            phone_number_id=phone_number_id,
        )

    async def remove_reaction(
        self, to: str, *, phone_number_id: str, message_id: str
    ) -> SendResult:
        """Retira la reacción puesta a un mensaje.

        Meta ya no documenta este comportamiento, aunque sigue funcionando: ver
        ``builders.build_remove_reaction``.
        """
        return await self.send_payload(
            builders.build_remove_reaction(to, message_id),
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
        """Envía una plantilla ya aprobada.

        Para plantillas de marketing existe además ``TemplatesClient.send_marketing``,
        que usa el endpoint optimizado de la Marketing Messages API.
        """
        return await self.send_payload(
            builders.build_template(to, name, language_code, components),
            phone_number_id=phone_number_id,
        )

    async def mark_read(
        self,
        *,
        phone_number_id: str,
        message_id: str,
        typing: bool = True,
        typing_type: str = "text",
    ) -> dict[str, Any]:
        """Marca un mensaje entrante como leído y muestra el indicador de escritura."""
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        payload = builders.build_mark_read(message_id, typing=typing, typing_type=typing_type)
        return await self._post_message(
            payload,
            phone_number_id=phone_number_id,
            access_token=credentials.access_token,
        )
