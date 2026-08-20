"""Transporte HTTP hacia la Graph API de Meta.

Un único ``httpx.AsyncClient`` compartido (keep-alive, pool de conexiones) con
reintentos gobernados por ``RetryPolicy`` y errores tipados de ``wacloud.errors``.

El transporte es agnóstico del negocio: recibe el ``access_token`` ya resuelto. Los
clientes de alto nivel (messages/templates) son quienes usan el ``CredentialResolver``
para obtenerlo.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from wacloud.config import DEFAULT_CONFIG, GraphConfig
from wacloud.error_codes import rule_for_code
from wacloud.errors import WaCloudError, WaTransportError, error_from_response
from wacloud.responses import (
    HTTP_ERROR_FLOOR,
    parse_json_body,
    safe_json,
    server_hint,
)
from wacloud.retry import DEFAULT_RETRY_POLICY, RetryPolicy

logger = logging.getLogger("wacloud.transport")

#: Hook opcional de rate limit. Se invoca antes de cada intento con el
#: phone_number_id (si se conoce); el host puede esperar/limitar por número.
RateLimitHook = Callable[[str | None], Awaitable[None]]

#: Función que ejecuta un intento concreto. La recibe ``_run`` para no duplicar el
#: bucle de reintentos entre peticiones JSON y descargas binarias.
Attempt = Callable[[httpx.AsyncClient], Awaitable[httpx.Response]]

_POOL_LIMITS = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=100,
    keepalive_expiry=30.0,
)


def _meta_processed_it(error: WaCloudError) -> bool:
    """Si el fallo demuestra que Meta miró la petición y la rechazó.

    Un código del catálogo (``error_codes``) lo demuestra: Meta la evaluó y dijo que no,
    así que repetirla no puede duplicar nada. Un 5xx sin código reconocible no demuestra
    nada — la petición pudo haberse procesado y perderse solo la respuesta.

    La distinción solo importa en peticiones no idempotentes; en las demás, repetir es
    gratis y el criterio de ``retryable`` basta.
    """
    return rule_for_code(error.code) is not None


class Transport:
    """Cliente HTTP con reintentos. Usable como context manager asíncrono."""

    def __init__(
        self,
        config: GraphConfig | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        retry_policy: RetryPolicy | None = None,
        rate_limit_hook: RateLimitHook | None = None,
    ) -> None:
        self._config = config or DEFAULT_CONFIG
        self._retry = retry_policy or DEFAULT_RETRY_POLICY
        self._external_client = client is not None
        self._client = client
        self._client_lock = asyncio.Lock()
        self._rate_limit_hook = rate_limit_hook

    @property
    def config(self) -> GraphConfig:
        return self._config

    async def __aenter__(self) -> Transport:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Cierra el cliente si lo creó el transporte (no si fue inyectado)."""
        if self._external_client:
            return
        client = self._client
        self._client = None
        if client is not None and not client.is_closed:
            await client.aclose()

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

    # -- Bucle de reintentos (compartido por todas las operaciones) ---------------

    async def _run(
        self,
        attempt_fn: Attempt,
        *,
        phone_number_id: str | None,
        idempotent: bool = True,
    ) -> httpx.Response:
        """Ejecuta ``attempt_fn`` con reintentos y devuelve la respuesta correcta.

        Lanza una subclase de ``WaCloudError`` si el error no es reintentable o si se
        agotan los intentos. El parseo del cuerpo queda para el llamador, que es quien
        sabe si espera JSON o bytes.

        ``idempotent`` a ``False`` restringe qué se reintenta: solo lo que Meta rechazó
        de forma reconocible. Ver ``_meta_processed_it``.
        """
        client = await self._get_client()
        last_error: WaCloudError | None = None

        for attempt in range(self._retry.max_retries + 1):
            if self._rate_limit_hook is not None:
                await self._rate_limit_hook(phone_number_id)

            try:
                response = await attempt_fn(client)
            except httpx.HTTPError as exc:
                last_error = WaTransportError(str(exc))
                # Un timeout o una conexión caída no dicen si Meta llegó a procesar la
                # petición. Reintentar a ciegas un envío significa, cuando sí la
                # procesó, un segundo mensaje al destinatario.
                if not idempotent or not self._retry.should_retry(attempt):
                    break
                await self._sleep_before_retry(attempt, None, last_error)
                continue

            if response.status_code < HTTP_ERROR_FLOOR:
                return response

            error = error_from_response(response.status_code, safe_json(response))
            if not error.retryable:
                raise error
            if not idempotent and not _meta_processed_it(error):
                raise error

            last_error = error
            hint = server_hint(response, error)
            if not self._retry.should_retry(attempt, required_wait=hint):
                break
            await self._sleep_before_retry(attempt, hint, error)

        # Aquí siempre hay un error: sin él habríamos devuelto la respuesta arriba.
        # No se usa assert porque ``python -O`` lo elimina y devolveríamos None.
        if last_error is None:  # pragma: no cover - inalcanzable
            raise WaTransportError("El transporte terminó sin respuesta ni error")
        raise last_error

    async def _sleep_before_retry(
        self, attempt: int, hint: float | None, error: WaCloudError
    ) -> None:
        delay = self._retry.delay_for(attempt, server_hint=hint)
        logger.warning(
            "wacloud: reintento %d/%d en %.2fs tras %s (código Meta: %s)",
            attempt + 1,
            self._retry.max_retries,
            delay,
            type(error).__name__,
            error.code,
        )
        if delay > 0:
            await asyncio.sleep(delay)

    # -- Operaciones públicas ----------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        access_token: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        phone_number_id: str | None = None,
        idempotent: bool = True,
    ) -> dict[str, Any]:
        """Petición JSON a un path versionado de la Graph API. Devuelve el cuerpo.

        ``idempotent`` a ``False`` para lo que no se puede repetir sin consecuencias
        visibles para un tercero — enviar un mensaje, en la práctica.
        """
        url = self._config.graph_url(path)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        async def attempt(client: httpx.AsyncClient) -> httpx.Response:
            return await client.request(method, url, json=json, params=params, headers=headers)

        response = await self._run(
            attempt, phone_number_id=phone_number_id, idempotent=idempotent
        )
        return parse_json_body(response)

    async def post_multipart(
        self,
        path: str,
        *,
        access_token: str,
        files: dict[str, Any],
        data: dict[str, Any] | None = None,
        phone_number_id: str | None = None,
    ) -> dict[str, Any]:
        """POST ``multipart/form-data``, para subir un medio a la Media API.

        No se fija ``Content-Type``: httpx lo genera con el ``boundary`` correcto, y
        ponerlo a mano rompe el cuerpo.
        """
        url = self._config.graph_url(path)
        headers = {"Authorization": f"Bearer {access_token}"}

        async def attempt(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(url, files=files, data=data, headers=headers)

        response = await self._run(attempt, phone_number_id=phone_number_id)
        return parse_json_body(response)

    async def post_binary(
        self,
        path: str,
        *,
        authorization: str,
        content: bytes,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """POST con el cuerpo binario crudo, para la Resumable Upload API.

        ``authorization`` se recibe entero (``"OAuth <token>"``) en vez de solo el token
        porque este endpoint **no usa el esquema ``Bearer``** del resto de la Graph API.
        """
        url = self._config.graph_url(path)
        headers = {"Authorization": authorization}
        if extra_headers:
            headers.update(extra_headers)

        async def attempt(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(url, content=content, headers=headers)

        response = await self._run(attempt, phone_number_id=None)
        return parse_json_body(response)

    async def get_bytes(
        self,
        url: str,
        *,
        access_token: str,
        phone_number_id: str | None = None,
    ) -> tuple[bytes, str | None]:
        """GET binario de una URL absoluta (p. ej. descarga de un medio de Meta).

        Devuelve ``(contenido, content_type)`` con el content type ya despojado de
        parámetros como ``; charset=utf-8``.
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        async def attempt(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(url, headers=headers)

        response = await self._run(attempt, phone_number_id=phone_number_id)
        content_type = response.headers.get("content-type")
        if content_type and ";" in content_type:
            content_type = content_type.split(";", 1)[0].strip()
        return response.content, content_type
