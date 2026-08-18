"""Jerarquía de errores de wacloud.

Permite al host distinguir errores reintentables (rate limit, 5xx, red) de los
definitivos (4xx de validación) sin inspeccionar códigos crudos.
"""
from __future__ import annotations

from typing import Any


class WaCloudError(Exception):
    """Error base de wacloud."""

    #: Si el host podría reintentar la operación tal cual.
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class WaTransportError(WaCloudError):
    """Fallo de red / conexión antes de obtener una respuesta HTTP."""

    retryable = True


class WaInvalidRequest(WaCloudError):
    """La Graph API rechazó la solicitud (4xx no reintentable: 400/401/403/404/422)."""

    retryable = False


class WaRateLimited(WaCloudError):
    """Meta aplicó rate limit (HTTP 429)."""

    retryable = True

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = 429,
        body: Any | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, body=body)
        self.retry_after_seconds = retry_after_seconds


class WaServerError(WaCloudError):
    """Error del lado de Meta (HTTP 5xx)."""

    retryable = True


def _meta_error_message(body: Any) -> str | None:
    """Extrae ``error.message`` de una respuesta de error de la Graph API."""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
    return None


def error_from_response(status_code: int, body: Any) -> WaCloudError:
    """Mapea un status HTTP a la excepción tipada correspondiente.

    Si Meta incluyó ``error.message`` en el body, se antepone al texto para que
    el host vea la causa real (p. ej. "Recipient phone number not in allowed
    list") en vez de un genérico "HTTP 400".
    """
    detail = _meta_error_message(body)
    base = f"Graph API respondió HTTP {status_code}"
    message = f"{base}: {detail}" if detail else base
    if status_code == 429:
        return WaRateLimited(message, status_code=status_code, body=body)
    if 500 <= status_code < 600:
        return WaServerError(message, status_code=status_code, body=body)
    return WaInvalidRequest(message, status_code=status_code, body=body)
