"""Interpretación de las respuestas HTTP de la Graph API.

Funciones puras separadas del transporte: aquí se decide *qué dice* una respuesta, y en
``transport`` *qué se hace* con ella. Se testean sin red ni reintentos.
"""

from __future__ import annotations

import json as jsonlib
from typing import Any

import httpx

from wacloud.errors import WaCloudError

#: Primer status que la Graph API considera error.
HTTP_ERROR_FLOOR = 400


def safe_json(response: httpx.Response) -> Any:
    """Cuerpo como JSON, o como texto si no lo es (un 502 de un proxy trae HTML)."""
    try:
        return response.json()
    except ValueError:
        return response.text


def parse_json_body(response: httpx.Response) -> dict[str, Any]:
    """Normaliza la respuesta a ``dict``.

    Algunos endpoints de Meta devuelven ``true`` o una lista en vez de un objeto; se
    envuelven para que el llamador siempre reciba la misma forma.
    """
    try:
        body = response.json()
    except ValueError:
        return {"ok": True, "raw": response.text}
    return body if isinstance(body, dict) else {"ok": True, "data": body}


def parse_retry_after(response: httpx.Response) -> float | None:
    """Header ``Retry-After`` en segundos, si viene y es numérico.

    Meta no lo documenta para la Cloud API, así que se trata como oportunista: si
    aparece se aprovecha, pero la política de backoff no depende de él.
    """
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_usage_hint(response: httpx.Response) -> float | None:
    """``estimated_time_to_regain_access`` de ``X-Business-Use-Case-Usage``, en segundos.

    Este es el mecanismo que Meta sí documenta para saber cuánto falta para recuperar
    el acceso. El header trae un JSON que mapea objeto de negocio a lista de entradas
    de uso, y el valor viene en **minutos**.

    Meta no publica el enum de ``type`` que emite WhatsApp, así que se recorren todas
    las entradas y se toma el máximo en vez de filtrar por un tipo concreto.
    """
    raw = response.headers.get("X-Business-Use-Case-Usage")
    if not raw:
        return None
    try:
        parsed = jsonlib.loads(raw)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None

    waits: list[float] = []
    for entries in parsed.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            minutes = entry.get("estimated_time_to_regain_access")
            if isinstance(minutes, bool) or not isinstance(minutes, (int, float)):
                continue
            if minutes > 0:
                waits.append(float(minutes) * 60.0)
    return max(waits) if waits else None


def server_hint(response: httpx.Response, error: WaCloudError) -> float | None:
    """Espera mínima sugerida, combinando todas las señales disponibles.

    Se toma la mayor: el suelo que impone el código de error de Meta, el header
    ``Retry-After`` y ``estimated_time_to_regain_access``. Quedarse corto provoca otro
    rechazo y, en algunos códigos, penalización adicional.
    """
    hints = [
        error.retry_after_seconds,
        parse_retry_after(response),
        parse_usage_hint(response),
    ]
    known = [h for h in hints if h is not None]
    return max(known) if known else None
