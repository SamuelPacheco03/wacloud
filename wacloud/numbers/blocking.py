"""Bloqueo de usuarios de WhatsApp para un número.

Es alcance número, como el resto de ``numbers/``, pero responsabilidad distinta:
aprovisionar una línea y moderar quién puede escribirle no cambian por los mismos
motivos. Por eso vive en su propio cliente en vez de engordar ``NumbersClient``.

Un usuario bloqueado deja de poder enviar mensajes al número. El bloqueo lo aplica Meta,
no la librería: el host no tiene que filtrar nada por su cuenta.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/block-users
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from wacloud.credentials import CredentialResolver
from wacloud.recipient import normalize_recipient
from wacloud.transport import Transport

#: Meta acepta como mucho 100 usuarios por llamada.
MAX_USERS_PER_CALL = 100

#: Tope de páginas al listar bloqueados, por si un cursor no avanzara.
_MAX_PAGES = 20

_BLOCK_USERS = "block_users"


class BlockResult(BaseModel):
    """Resultado de bloquear o desbloquear.

    Meta responde por usuario, no por lote: puede aceptar unos y rechazar otros en la
    misma llamada. Por eso hay dos listas y no un solo booleano — dar por bloqueado a
    alguien que Meta rechazó dejaría un agujero silencioso en la moderación.
    """

    #: ``wa_id`` de los que sí se procesaron.
    succeeded: list[str] = Field(default_factory=list)
    #: Los que Meta rechazó, con su motivo: ``{"input": ..., "reason": ...}``.
    failed: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_meta(cls, body: dict[str, Any], *, key: str) -> BlockResult:
        block = body.get(_BLOCK_USERS)
        payload = block if isinstance(block, dict) else {}

        added = payload.get(key)
        failed = payload.get("failed_users")
        return cls(
            succeeded=[
                str(item["wa_id"])
                for item in (added if isinstance(added, list) else [])
                if isinstance(item, dict) and item.get("wa_id")
            ],
            failed=[
                i for i in (failed if isinstance(failed, list) else []) if isinstance(i, dict)
            ],
            raw=body,
        )

    @property
    def all_succeeded(self) -> bool:
        return not self.failed


class BlockedUsersClient:
    """Lista de bloqueo de un número."""

    def __init__(self, transport: Transport, resolver: CredentialResolver) -> None:
        self._transport = transport
        self._resolver = resolver

    def _payload(self, users: list[str]) -> dict[str, Any]:
        """Normaliza los destinatarios y arma el cuerpo que espera Meta."""
        if not users:
            raise ValueError("se requiere al menos un usuario")
        if len(users) > MAX_USERS_PER_CALL:
            raise ValueError(
                f"Meta admite {MAX_USERS_PER_CALL} usuarios por llamada, "
                f"se dieron {len(users)}"
            )
        return {
            "messaging_product": "whatsapp",
            _BLOCK_USERS: [{"user": normalize_recipient(u)} for u in users],
        }

    async def block(self, phone_number_id: str, users: list[str]) -> BlockResult:
        """Bloquea usuarios para este número.

        Mira siempre ``failed``: Meta puede rechazar parte del lote y aceptar el resto.
        """
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        response = await self._transport.request(
            "POST",
            f"/{phone_number_id}/{_BLOCK_USERS}",
            access_token=credentials.access_token,
            json=self._payload(users),
            phone_number_id=phone_number_id,
        )
        return BlockResult.from_meta(response, key="added_users")

    async def unblock(self, phone_number_id: str, users: list[str]) -> BlockResult:
        """Levanta el bloqueo de estos usuarios."""
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        response = await self._transport.request(
            "DELETE",
            f"/{phone_number_id}/{_BLOCK_USERS}",
            access_token=credentials.access_token,
            json=self._payload(users),
            phone_number_id=phone_number_id,
        )
        return BlockResult.from_meta(response, key="removed_users")

    async def list_all(self, phone_number_id: str, *, page_size: int = 100) -> list[str]:
        """``wa_id`` de todos los usuarios bloqueados, siguiendo la paginación."""
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        blocked: list[str] = []
        after: str | None = None

        for _ in range(_MAX_PAGES):
            params: dict[str, Any] = {"limit": page_size}
            if after:
                params["after"] = after
            response = await self._transport.request(
                "GET",
                f"/{phone_number_id}/{_BLOCK_USERS}",
                access_token=credentials.access_token,
                params=params,
                phone_number_id=phone_number_id,
            )
            data = response.get("data")
            if isinstance(data, list):
                blocked.extend(
                    str(item["wa_id"])
                    for item in data
                    if isinstance(item, dict) and item.get("wa_id")
                )

            next_cursor = _next_cursor(response)
            if not next_cursor or next_cursor == after:
                break
            after = next_cursor

        return blocked


def _next_cursor(response: dict[str, Any]) -> str | None:
    """Cursor ``after`` de la página siguiente, solo si Meta indicó que hay más."""
    paging = response.get("paging")
    if not isinstance(paging, dict) or not paging.get("next"):
        return None
    cursors = paging.get("cursors")
    if not isinstance(cursors, dict):
        return None
    after = cursors.get("after")
    return after if isinstance(after, str) and after else None
