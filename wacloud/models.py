"""Resultados normalizados de la Graph API hacia el host.

Estos modelos describen *respuestas* ya interpretadas, no los payloads crudos (esos los
arman los builders). Mantienen al host desacoplado de la forma exacta de la respuesta de
Meta, que cambia entre versiones de la Graph API.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


def extract_message_id(body: dict[str, Any]) -> str | None:
    """Extrae el ``wamid`` de una respuesta de envío.

    Forma típica: ``{"messages": [{"id": "wamid..."}], "contacts": [...]}``.
    """
    messages = body.get("messages")
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, dict):
            mid = first.get("id")
            if isinstance(mid, str) and mid:
                return mid
    return None


def extract_message_status(body: dict[str, Any]) -> str | None:
    """Extrae ``messages[0].message_status`` si Meta lo incluyó.

    Vale ``accepted``, ``held_for_quality_assessment`` o ``paused``. Un envío aceptado
    con estado ``paused`` **no se va a entregar**, así que el host necesita verlo: un
    ``SendResult`` con ``message_id`` no garantiza entrega.
    """
    messages = body.get("messages")
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, dict):
            status = first.get("message_status")
            if isinstance(status, str) and status:
                return status
    return None


class SendResult(BaseModel):
    """Resultado de un envío individual aceptado por Meta."""

    message_id: str | None = None
    #: ``accepted`` | ``held_for_quality_assessment`` | ``paused``, si Meta lo devolvió.
    message_status: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_response(cls, body: dict[str, Any]) -> SendResult:
        return cls(
            message_id=extract_message_id(body),
            message_status=extract_message_status(body),
            raw=body,
        )


class BatchSendResult(BaseModel):
    """Resultado de un mensaje dentro de un envío en lote.

    El lote es secuencial y preserva el orden: hay un ``BatchSendResult`` por cada
    payload de entrada, en la misma posición. ``ok`` indica si Meta lo aceptó; si no,
    ``error`` trae el motivo y ``code`` el código de Meta para decidir sin parsear texto.
    """

    ok: bool
    message_id: str | None = None
    error: str | None = None
    #: Código de error de Meta (``error.code``), cuando el fallo vino de la Graph API.
    code: int | None = None
    raw: dict[str, Any] | None = None

    @classmethod
    def accepted(cls, body: dict[str, Any]) -> BatchSendResult:
        return cls(ok=True, message_id=extract_message_id(body), raw=body)

    @classmethod
    def failed(cls, error: str, *, code: int | None = None) -> BatchSendResult:
        return cls(ok=False, error=error, code=code)


class TemplateInfo(BaseModel):
    """Resumen de una plantilla gestionada en la WABA.

    ``status`` es el estado de aprobación de Meta: ``APPROVED``, ``PENDING``,
    ``REJECTED``, ``PAUSED``, ``DISABLED``, ``IN_APPEAL``…
    """

    id: str | None = None
    name: str | None = None
    language: str | None = None
    status: str | None = None
    category: str | None = None
    #: ``POSITIONAL`` o ``NAMED``. Determina la forma de los parámetros al enviar.
    parameter_format: str | None = None
    #: Presente cuando ``status`` es ``REJECTED``.
    rejected_reason: str | None = None
    components: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def from_meta(cls, item: dict[str, Any]) -> TemplateInfo:
        components = item.get("components")
        return cls(
            id=_as_str(item.get("id")),
            name=item.get("name"),
            language=item.get("language"),
            status=item.get("status"),
            category=item.get("category"),
            parameter_format=item.get("parameter_format"),
            rejected_reason=item.get("rejected_reason"),
            components=components if isinstance(components, list) else [],
        )


def _as_str(value: Any) -> str | None:
    """Meta devuelve los IDs de plantilla como número en unos sitios y string en otros."""
    if value is None:
        return None
    return str(value)
