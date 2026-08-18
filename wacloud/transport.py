"""Transporte HTTP hacia la Graph API de Meta.

Un único ``httpx.AsyncClient`` compartido (keep-alive, pool de conexiones) más
reintentos con backoff exponencial y jitter para 429/5xx y errores de red. Los
errores se devuelven tipados (ver ``wacloud.errors``).

El transporte es agnóstico del negocio: recibe el ``access_token`` ya resuelto.
Los clientes de alto nivel (messages/templates) son quienes usan el
``CredentialResolver`` para obtenerlo.
"""
from __future__ import annotations

import asyncio
import random
from typing import Any, Awaitable, Callable

import httpx

from wacloud.config import DEFAULT_CONFIG, GraphConfig
from wacloud.errors import (
    WaCloudError,
    WaRateLimited,
    WaTransportError,
    error_from_response,
)

#: Hook opcional de rate limit. Se invoca antes de cada intento con el
#: phone_number_id (si se conoce); el host puede esperar/limitar por número.
RateLimitHook = Callable[[str | None], Awaitable[None]]

_POOL_LIMITS = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=100,
    keepalive_expiry=30.0,
)


class Transport:
    def __init__(
        self,
        config: GraphConfig | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        rate_limit_hook: RateLimitHook | None = None,
    ) -> None:
        self._config = config or DEFAULT_CONFIG
        self._external_client = client is not None
        self._client = client
        self._client_lock = asyncio.Lock()
        self._rate_limit_hook = rate_limit_hook

    async def _get_client(self) -> httpx.AsyncClient:
        client = self._client
        if client is not None and not client.is_closed:
            return client
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                timeout = httpx.Timeout(
                    connect=self._config.connect_timeout,
                    read=self._config.read_timeout,
                    write=self._config.read_timeout,
                    pool=self._config.connect_timeout,
                )
                self._client = httpx.AsyncClient(timeout=timeout, limits=_POOL_LIMITS)
            return self._client

    async def aclose(self) -> None:
        """Cierra el cliente si lo creó el transporte (no si fue inyectado)."""
        if self._external_client:
            return
        client = self._client
        self._client = None
        if client is not None and not client.is_closed:
            await client.aclose()

    def _backoff_delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None and retry_after >= 0:
            return min(retry_after, self._config.backoff_max_seconds)
        # Exponencial con jitter completo.
        raw = self._config.backoff_base_seconds * (2 ** attempt)
        capped = min(raw, self._config.backoff_max_seconds)
        return random.uniform(0, capped)

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    async def request(
        self,
        method: str,
        path: str,
        *,
        access_token: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        phone_number_id: str | None = None,
    ) -> dict[str, Any]:
        """Ejecuta una petición a la Graph API con reintentos. Devuelve el JSON.

        Lanza una subclase de ``WaCloudError`` si se agotan los reintentos o si el
        error no es reintentable.
        """
        url = self._config.graph_url(path)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        client = await self._get_client()

        last_error: WaCloudError | None = None
        # Total de intentos = 1 inicial + max_retries.
        for attempt in range(self._config.max_retries + 1):
            if self._rate_limit_hook is not None:
                await self._rate_limit_hook(phone_number_id)

            try:
                response = await client.request(
                    method, url, json=json, params=params, headers=headers
                )
            except httpx.HTTPError as exc:
                last_error = WaTransportError(str(exc))
                await self._maybe_sleep(attempt, None, last_error)
                continue

            if response.status_code < 400:
                return self._parse_body(response)

            body = self._safe_json(response)
            error = error_from_response(response.status_code, body)
            if not error.retryable:
                raise error

            last_error = error
            retry_after = (
                error.retry_after_seconds
                if isinstance(error, WaRateLimited)
                else self._parse_retry_after(response)
            )
            await self._maybe_sleep(attempt, retry_after, error)

        # Reintentos agotados.
        assert last_error is not None  # garantizado por el loop
        raise last_error

    async def get_bytes(
        self,
        url: str,
        *,
        access_token: str,
        phone_number_id: str | None = None,
    ) -> tuple[bytes, str | None]:
        """GET binario de una URL absoluta (p. ej. descarga de un medio de Meta).

        Reintenta igual que ``request``. Devuelve ``(contenido, content_type)``.
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        client = await self._get_client()

        last_error: WaCloudError | None = None
        for attempt in range(self._config.max_retries + 1):
            if self._rate_limit_hook is not None:
                await self._rate_limit_hook(phone_number_id)

            try:
                response = await client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                last_error = WaTransportError(str(exc))
                await self._maybe_sleep(attempt, None, last_error)
                continue

            if response.status_code < 400:
                content_type = response.headers.get("content-type")
                if content_type and ";" in content_type:
                    content_type = content_type.split(";", 1)[0].strip()
                return response.content, content_type

            error = error_from_response(response.status_code, self._safe_json(response))
            if not error.retryable:
                raise error
            last_error = error
            retry_after = (
                error.retry_after_seconds
                if isinstance(error, WaRateLimited)
                else self._parse_retry_after(response)
            )
            await self._maybe_sleep(attempt, retry_after, error)

        assert last_error is not None
        raise last_error

    async def _maybe_sleep(
        self, attempt: int, retry_after: float | None, error: WaCloudError
    ) -> None:
        if attempt >= self._config.max_retries:
            # Último intento: no dormir, dejar que el caller reciba el error.
            return
        await asyncio.sleep(self._backoff_delay(attempt, retry_after))

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text

    @staticmethod
    def _parse_body(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            return {"ok": True, "raw": response.text}
        return body if isinstance(body, dict) else {"ok": True, "data": body}
