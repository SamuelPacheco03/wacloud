"""Constructores compartidos por los tests.

Centralizados para que un cambio en la firma de ``Transport`` o de los clientes se
arregle en un sitio y no en cinco archivos.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from wacloud.config import GraphConfig
from wacloud.credentials import StaticCredentialResolver, WaCredentials
from wacloud.messages import MessagesClient
from wacloud.retry import RetryPolicy
from wacloud.templates import TemplatesClient
from wacloud.transport import Transport

Handler = Callable[[httpx.Request], httpx.Response]


def fast_policy(max_retries: int = 0) -> RetryPolicy:
    """Política sin esperas: los tests no deben tardar por culpa del backoff."""
    return RetryPolicy(
        max_retries=max_retries,
        base_seconds=0.0,
        multiplier=1.0,
        max_seconds=0.0,
        jitter=False,
    )


def make_transport(
    handler: Handler,
    *,
    max_retries: int = 0,
    config: GraphConfig | None = None,
) -> Transport:
    """Transport sobre ``httpx.MockTransport``: nunca sale a la red."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return Transport(
        config or GraphConfig(),
        client=client,
        retry_policy=fast_policy(max_retries),
    )


def make_resolver() -> StaticCredentialResolver:
    return StaticCredentialResolver(
        WaCredentials(phone_number_id="PNID", access_token="tok", waba_id="WABA")
    )


def make_messages_client(handler: Handler, *, max_retries: int = 0) -> MessagesClient:
    return MessagesClient(make_transport(handler, max_retries=max_retries), make_resolver())


def make_templates_client(
    handler: Handler, *, cache_ttl: float = 60.0, max_retries: int = 0
) -> TemplatesClient:
    return TemplatesClient(
        make_transport(handler, max_retries=max_retries),
        make_resolver(),
        cache_ttl_seconds=cache_ttl,
    )


def capturing_handler(
    response: dict[str, Any] | None = None, *, status: int = 200
) -> tuple[dict[str, Any], Handler]:
    """Handler que registra la petición recibida y devuelve una respuesta fija.

    Devuelve ``(capturado, handler)``. ``capturado`` se rellena al ejecutarse la
    petición, con ``path``, ``method``, ``params`` y ``body`` (el JSON ya parseado).

    Existe aquí y no en cada archivo de tests porque casi todos necesitan lo mismo:
    comprobar a qué endpoint se llamó y con qué cuerpo.
    """
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["params"] = dict(request.url.params)
        if request.content:
            try:
                captured["body"] = json.loads(request.content.decode())
            except ValueError:
                captured["raw_body"] = request.content
        return httpx.Response(status, json=response if response is not None else {})

    return captured, handler


def ok_handler(response: dict[str, Any] | None = None) -> Handler:
    """Handler mínimo que siempre responde 200. Para tests que no inspeccionan la red."""
    _, handler = capturing_handler(response if response is not None else {"success": True})
    return handler


def accepted_handler(message_id: str = "wamid.OK") -> tuple[dict[str, Any], Handler]:
    """Handler que simula un envío aceptado por Meta."""
    return capturing_handler({"messages": [{"id": message_id}]})
