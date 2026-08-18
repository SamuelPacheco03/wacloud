"""Tipos de entrada/salida del envío de mensajes.

Estos modelos describen *resultados* normalizados de la Graph API, no los
payloads crudos (esos los arman los builders). Mantienen al host desacoplado de
la forma exacta de la respuesta de Meta.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def extract_message_id(body: dict[str, Any]) -> str | None:
    """Extrae el ``wamid`` de una respuesta de envío de Meta.

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


class SendResult(BaseModel):
    """Resultado de un envío individual aceptado por Meta."""

    message_id: str | None = None
    raw: dict[str, Any] = {}

    @classmethod
    def from_response(cls, body: dict[str, Any]) -> "SendResult":
        return cls(message_id=extract_message_id(body), raw=body)


class BatchSendResult(BaseModel):
    """Resultado de un mensaje dentro de un envío batch.

    El batch es secuencial y preserva el orden: hay un ``BatchSendResult`` por
    cada payload de entrada, en la misma posición. ``ok`` indica si Meta lo
    aceptó; si no, ``error`` trae el motivo.
    """

    ok: bool
    message_id: str | None = None
    error: str | None = None
    raw: dict[str, Any] | None = None

    @classmethod
    def accepted(cls, body: dict[str, Any]) -> "BatchSendResult":
        return cls(ok=True, message_id=extract_message_id(body), raw=body)

    @classmethod
    def failed(cls, error: str) -> "BatchSendResult":
        return cls(ok=False, error=error)


class TemplateInfo(BaseModel):
    """Resumen de una plantilla de mensaje gestionada en la WABA.

    ``status`` es el estado de aprobación de Meta (APPROVED, PENDING, REJECTED…).
    """

    id: str | None = None
    name: str | None = None
    language: str | None = None
    status: str | None = None
    category: str | None = None
    components: list[dict[str, Any]] = []

    @classmethod
    def from_meta(cls, item: dict[str, Any]) -> "TemplateInfo":
        components = item.get("components")
        return cls(
            id=item.get("id"),
            name=item.get("name"),
            language=item.get("language"),
            status=item.get("status"),
            category=item.get("category"),
            components=components if isinstance(components, list) else [],
        )
