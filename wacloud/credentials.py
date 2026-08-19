"""Resolución de credenciales por número (inyectada por el host).

La librería NUNCA lee tokens de variables de entorno ni de una base de datos. El
host implementa ``CredentialResolver`` (p. ej. leyendo de una tabla y descifrando
con Fernet) y se lo pasa a los clientes de wacloud.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class WaCredentials(BaseModel):
    """Credenciales de un número/WABA, ya descifradas por el host."""

    phone_number_id: str = Field(..., min_length=1)
    access_token: str = Field(..., min_length=1)
    waba_id: str | None = None
    #: App secret de Meta para validar la firma del webhook (X-Hub-Signature-256).
    app_secret: str | None = None


@runtime_checkable
class CredentialResolver(Protocol):
    """Contrato que el host implementa para entregar credenciales a wacloud."""

    async def for_phone_number_id(self, phone_number_id: str) -> WaCredentials:
        """Credenciales del número emisor (envío de mensajes/plantillas)."""
        ...

    async def for_waba_id(self, waba_id: str) -> WaCredentials:
        """Credenciales por WABA (gestión de plantillas, validación de webhook)."""
        ...


class StaticCredentialResolver:
    """Resolver de conveniencia para tests/un solo número.

    No usar en producción multi-número: mantiene credenciales en memoria.
    """

    def __init__(self, credentials: WaCredentials) -> None:
        self._credentials = credentials

    async def for_phone_number_id(self, phone_number_id: str) -> WaCredentials:
        return self._credentials

    async def for_waba_id(self, waba_id: str) -> WaCredentials:
        return self._credentials
