"""Contrato de almacenamiento de medios (inyectado por el host).

La librería no sabe de Cloudflare R2, S3 ni disco: define el protocolo y el host
aporta la implementación concreta (p. ej. ``R2StorageBackend`` con aioboto3).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class StoredMedia(BaseModel):
    """Referencia a un objeto ya almacenado por el backend del host."""

    key: str
    content_type: str
    size_bytes: int
    sha256: str | None = None


@runtime_checkable
class StorageBackend(Protocol):
    """Contrato mínimo de almacenamiento de objetos."""

    async def put(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
    ) -> StoredMedia:
        """Guarda ``data`` bajo ``key`` y devuelve la referencia almacenada."""
        ...

    async def presigned_get_url(self, *, key: str, ttl_seconds: int) -> str:
        """Devuelve una URL temporal de lectura para ``key``."""
        ...
