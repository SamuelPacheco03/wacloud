"""Jerarquía de errores de wacloud.

El objetivo es que el host decida qué hacer **sin parsear cadenas de texto**. Todo
lo que Meta comunica de forma estructurada (``error.code``, ``error_data.details``,
``fbtrace_id``) se expone como atributo tipado.

``retryable`` se determina, en este orden:

1. Por el ``error.code`` de Meta, que es la fuente que Meta manda usar.
2. Si el código no está catalogado, por el status HTTP (429 y 5xx).

Referencia: https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes
"""

from __future__ import annotations

from typing import Any

from wacloud.error_codes import (
    HTTP_SERVER_ERROR_CEIL,
    HTTP_SERVER_ERROR_FLOOR,
    HTTP_TOO_MANY_REQUESTS,
    RetryRule,
    rule_for_code,
    rule_for_status,
)


class WaCloudError(Exception):
    """Error base de wacloud.

    Atributos relevantes para el host:

    - ``code``: código de error de Meta (``error.code``). ``None`` si no vino.
    - ``retryable``: si tiene sentido reintentar la operación tal cual.
    - ``retry_after_seconds``: espera mínima antes de reintentar, si se conoce.
    - ``details``: ``error_data.details``, el texto que explica la causa concreta.
    - ``fbtrace_id``: identificador de la traza de Meta, útil para abrir soporte.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any | None = None,
        code: int | None = None,
        details: str | None = None,
        fbtrace_id: str | None = None,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.code = code
        self.details = details
        self.fbtrace_id = fbtrace_id
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class WaTransportError(WaCloudError):
    """Fallo de red o conexión antes de obtener una respuesta HTTP."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class WaInvalidRequest(WaCloudError):
    """Meta rechazó la solicitud de forma definitiva (validación, permisos, política)."""


class WaRateLimited(WaCloudError):
    """Se alcanzó un límite de Meta (throughput, pair rate limit, cupo de la app)."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class WaServerError(WaCloudError):
    """Error del lado de Meta (HTTP 5xx) sin código catalogado."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class MetaError:
    """Vista estructurada del objeto ``error`` de una respuesta de la Graph API.

    Meta devuelve el error anidado bajo la clave ``error``; los campos son opcionales
    y el body puede no ser ni siquiera un objeto (ante un 502 de un proxy llega HTML).
    Por eso cada extracción es defensiva.
    """

    __slots__ = ("code", "details", "fbtrace_id", "message", "type")

    def __init__(
        self,
        *,
        code: int | None = None,
        message: str | None = None,
        details: str | None = None,
        fbtrace_id: str | None = None,
        type: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details
        self.fbtrace_id = fbtrace_id
        self.type = type

    @classmethod
    def from_body(cls, body: Any) -> MetaError:
        if not isinstance(body, dict):
            return cls()
        error = body.get("error")
        if not isinstance(error, dict):
            return cls()

        error_data = error.get("error_data")
        details = None
        if isinstance(error_data, dict):
            details = _clean_str(error_data.get("details"))

        return cls(
            code=_clean_int(error.get("code")),
            message=_clean_str(error.get("message")),
            details=details,
            fbtrace_id=_clean_str(error.get("fbtrace_id")),
            type=_clean_str(error.get("type")),
        )

    def describe(self, status_code: int) -> str:
        """Texto legible para el mensaje de la excepción."""
        parts = [f"Graph API respondió HTTP {status_code}"]
        if self.code is not None:
            parts.append(f"(código {self.code})")
        tail = self.details or self.message
        base = " ".join(parts)
        return f"{base}: {tail}" if tail else base


def _clean_str(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _clean_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


#: Códigos que sí son un límite de ritmo. Meta los devuelve con status variados, no
#: siempre 429, así que clasificar solo por HTTP los dejaría como errores genéricos.
_RATE_LIMIT_CODES = frozenset({4, 80007, 80008, 130429, 131056})


def _exception_type(status_code: int, code: int | None, rule: RetryRule) -> type[WaCloudError]:
    """Elige la clase de excepción. El código de Meta manda sobre el status HTTP.

    El caso que obliga a este orden: ``131050`` (el usuario rechazó el marketing) llega
    con HTTP 429. Clasificarlo por status daría un ``WaRateLimited`` no reintentable,
    que es una contradicción: el host lo trataría como un problema de ritmo y volvería a
    intentarlo más tarde, cuando en realidad no debe enviarse nunca más.
    """
    if code in _RATE_LIMIT_CODES:
        return WaRateLimited
    if code is not None and not rule.retryable:
        return WaInvalidRequest
    if status_code == HTTP_TOO_MANY_REQUESTS:
        return WaRateLimited
    if HTTP_SERVER_ERROR_FLOOR <= status_code < HTTP_SERVER_ERROR_CEIL:
        return WaServerError
    return WaInvalidRequest


def error_from_response(status_code: int, body: Any) -> WaCloudError:
    """Mapea una respuesta de error de la Graph API a una excepción tipada."""
    meta = MetaError.from_body(body)
    rule: RetryRule = rule_for_code(meta.code) or rule_for_status(status_code)
    exc_type = _exception_type(status_code, meta.code, rule)

    return exc_type(
        meta.describe(status_code),
        status_code=status_code,
        body=body,
        code=meta.code,
        details=meta.details,
        fbtrace_id=meta.fbtrace_id,
        retryable=rule.retryable,
        retry_after_seconds=rule.min_wait_seconds or None,
    )
