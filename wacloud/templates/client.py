"""Gestión de plantillas en la WABA + envío de plantillas de marketing.

``TemplatesClient`` cubre el ciclo de vida de las plantillas contra
``/{waba_id}/message_templates`` (crear, listar, borrar, consultar estado de
aprobación) y el envío por el endpoint especial de marketing
``/{phone_number_id}/marketing_messages``.

El listado tiene un **cache en memoria con TTL** por WABA (la lista de plantillas
cambia poco y Meta aplica rate limit). Crear o borrar invalida el cache de esa
WABA.
"""
from __future__ import annotations

import time
from typing import Any

from wacloud.config import DEFAULT_CONFIG, GraphConfig
from wacloud.credentials import CredentialResolver
from wacloud.models import SendResult, TemplateInfo
from wacloud.templates import builders
from wacloud.transport import Transport


class _TemplateCache:
    """Cache simple por WABA con expiración por tiempo."""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, list[TemplateInfo]]] = {}

    def get(self, waba_id: str) -> list[TemplateInfo] | None:
        entry = self._store.get(waba_id)
        if entry is None:
            return None
        stored_at, value = entry
        if (time.monotonic() - stored_at) > self._ttl:
            self._store.pop(waba_id, None)
            return None
        return value

    def set(self, waba_id: str, value: list[TemplateInfo]) -> None:
        self._store[waba_id] = (time.monotonic(), value)

    def invalidate(self, waba_id: str) -> None:
        self._store.pop(waba_id, None)


class TemplatesClient:
    def __init__(
        self,
        transport: Transport,
        resolver: CredentialResolver,
        *,
        config: GraphConfig | None = None,
        cache_ttl_seconds: float = 60.0,
    ) -> None:
        self._transport = transport
        self._resolver = resolver
        self._config = config or DEFAULT_CONFIG
        self._cache = _TemplateCache(cache_ttl_seconds)

    async def create(
        self,
        waba_id: str,
        *,
        name: str,
        language: str,
        category: str,
        components: list[dict[str, Any]],
        parameter_format: str | None = None,
    ) -> TemplateInfo:
        """Crea una plantilla en la WABA. Meta responde id + estado (p. ej. PENDING)."""
        credentials = await self._resolver.for_waba_id(waba_id)
        body: dict[str, Any] = {
            "name": str(name).strip(),
            "language": language,
            "category": category,
            "components": components,
        }
        if parameter_format:
            body["parameter_format"] = parameter_format
        response = await self._transport.request(
            "POST",
            f"/{waba_id}/message_templates",
            access_token=credentials.access_token,
            json=body,
        )
        self._cache.invalidate(waba_id)
        return TemplateInfo.from_meta(response)

    async def list(
        self, waba_id: str, *, use_cache: bool = True, limit: int = 100
    ) -> list[TemplateInfo]:
        """Lista las plantillas de la WABA (con cache TTL opcional)."""
        if use_cache:
            cached = self._cache.get(waba_id)
            if cached is not None:
                return cached
        credentials = await self._resolver.for_waba_id(waba_id)
        response = await self._transport.request(
            "GET",
            f"/{waba_id}/message_templates",
            access_token=credentials.access_token,
            params={"limit": limit},
        )
        data = response.get("data")
        templates = [
            TemplateInfo.from_meta(item)
            for item in (data if isinstance(data, list) else [])
        ]
        self._cache.set(waba_id, templates)
        return templates

    async def status(self, waba_id: str, name: str) -> str | None:
        """Estado de aprobación de una plantilla por nombre (None si no existe)."""
        templates = await self.list(waba_id)
        for template in templates:
            if template.name == name:
                return template.status
        return None

    async def delete(
        self, waba_id: str, *, name: str, hsm_id: str | None = None
    ) -> dict[str, Any]:
        """Borra una plantilla por nombre (opcionalmente una versión por ``hsm_id``)."""
        credentials = await self._resolver.for_waba_id(waba_id)
        params: dict[str, Any] = {"name": str(name).strip()}
        if hsm_id:
            params["hsm_id"] = hsm_id
        response = await self._transport.request(
            "DELETE",
            f"/{waba_id}/message_templates",
            access_token=credentials.access_token,
            params=params,
        )
        self._cache.invalidate(waba_id)
        return response

    async def send_marketing(
        self, payload: dict[str, Any], *, phone_number_id: str
    ) -> SendResult:
        """Envía una plantilla de marketing (payload de ``build_marketing_template``)."""
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        response = await self._transport.request(
            "POST",
            f"/{phone_number_id}/marketing_messages",
            access_token=credentials.access_token,
            json=payload,
            phone_number_id=phone_number_id,
        )
        return SendResult.from_response(response)

    async def send_marketing_template(
        self,
        *,
        phone_number_id: str,
        name: str,
        language_code: str,
        components: list[dict[str, Any]] | None = None,
        to: str | None = None,
        recipient: str | None = None,
        product_policy: str | None = None,
        message_activity_sharing: bool | None = None,
    ) -> SendResult:
        """Atajo: arma el payload de marketing y lo envía."""
        payload = builders.build_marketing_template(
            name=name,
            language_code=language_code,
            components=components,
            to=to,
            recipient=recipient,
            product_policy=product_policy,
            message_activity_sharing=message_activity_sharing,
        )
        return await self.send_marketing(payload, phone_number_id=phone_number_id)
