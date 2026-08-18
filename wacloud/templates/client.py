"""Gestión de plantillas en la WABA y envío por la Marketing Messages API.

``TemplatesClient`` cubre el ciclo de vida contra ``/{waba_id}/message_templates``
(crear, listar, borrar, consultar estado) y el envío por el endpoint optimizado
``/{phone_number_id}/marketing_messages``.

El listado tiene un **cache en memoria con TTL** por WABA: la lista cambia poco y Meta
limita estas llamadas a 200/h por WABA (5.000/h si tiene un número registrado). Crear o
borrar invalida el cache de esa WABA.
"""

from __future__ import annotations

import time
from typing import Any

from wacloud.credentials import CredentialResolver
from wacloud.models import SendResult, TemplateInfo
from wacloud.templates import builders
from wacloud.templates.definition import build_definition
from wacloud.templates.enums import ParameterFormat, TemplateCategory
from wacloud.transport import Transport

#: Tamaño de página por defecto al listar plantillas.
_DEFAULT_PAGE_SIZE = 100
#: Tope de páginas al recorrer el listado completo, por si Meta devolviera un cursor
#: que no avanza. Evita un bucle infinito consumiendo cupo de API.
_MAX_PAGES = 50


class _TemplateCache:
    """Cache por WABA con expiración por tiempo.

    Usa ``time.monotonic`` porque no retrocede si cambia la hora del sistema.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, list[TemplateInfo]]] = {}

    def get(self, waba_id: str) -> list[TemplateInfo] | None:
        entry = self._store.get(waba_id)
        if entry is None:
            return None
        stored_at, value = entry
        # Comparación inclusiva: con ttl=0 la entrada debe considerarse expirada
        # siempre, no servirse mientras el reloj no haya avanzado.
        if (time.monotonic() - stored_at) >= self._ttl:
            self._store.pop(waba_id, None)
            return None
        return value

    def set(self, waba_id: str, value: list[TemplateInfo]) -> None:
        self._store[waba_id] = (time.monotonic(), value)

    def invalidate(self, waba_id: str) -> None:
        self._store.pop(waba_id, None)


class TemplatesClient:
    def __init__(
        self,
        transport: Transport,
        resolver: CredentialResolver,
        *,
        cache_ttl_seconds: float = 60.0,
    ) -> None:
        self._transport = transport
        self._resolver = resolver
        self._cache = _TemplateCache(cache_ttl_seconds)

    # -- Gestión del ciclo de vida -----------------------------------------------

    async def create(
        self,
        waba_id: str,
        *,
        name: str,
        language: str,
        category: TemplateCategory | str,
        components: list[dict[str, Any]],
        parameter_format: ParameterFormat | str | None = None,
        message_send_ttl_seconds: int | None = None,
    ) -> TemplateInfo:
        """Crea una plantilla. Meta responde con el id y el estado inicial (``PENDING``).

        Los componentes se validan antes de salir (nombre, unicidad, coherencia del
        formato de variables). Merece la pena porque Meta limita la creación a 100
        plantillas por hora y WABA (código ``80008``) y el rechazo llega por webhook
        minutos u horas después.

        Si borras una plantilla aprobada, Meta no deja reutilizar el nombre en 30 días.
        """
        body = build_definition(
            name=name,
            language=language,
            category=category,
            components=components,
            parameter_format=parameter_format,
            message_send_ttl_seconds=message_send_ttl_seconds,
        )
        credentials = await self._resolver.for_waba_id(waba_id)
        response = await self._transport.request(
            "POST",
            f"/{waba_id}/message_templates",
            access_token=credentials.access_token,
            json=body,
        )
        self._cache.invalidate(waba_id)
        return TemplateInfo.from_meta(response)

    async def edit(
        self,
        template_id: str,
        *,
        waba_id: str,
        components: list[dict[str, Any]] | None = None,
        category: str | None = None,
        parameter_format: str | None = None,
        message_send_ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Edita una plantilla existente (``POST /{template_id}``).

        Restricciones de Meta: ``name`` y ``language`` no son editables; la categoría de
        una plantilla ``APPROVED`` no se puede cambiar; solo se editan plantillas en
        estado ``APPROVED``, ``REJECTED`` o ``PAUSED``. Una aprobada admite 10 ediciones
        en 30 días y 1 en 24 horas; las rechazadas o pausadas, ilimitadas.

        **Los componentes se reemplazan por completo**: no existe edición parcial, así
        que hay que enviar el array entero aunque solo cambie un texto.
        """
        credentials = await self._resolver.for_waba_id(waba_id)
        body: dict[str, Any] = {}
        if components is not None:
            body["components"] = components
        if category is not None:
            body["category"] = category
        if parameter_format is not None:
            body["parameter_format"] = parameter_format
        if message_send_ttl_seconds is not None:
            body["message_send_ttl_seconds"] = message_send_ttl_seconds
        if not body:
            raise ValueError("no se indicó ningún campo a editar")

        response = await self._transport.request(
            "POST",
            f"/{template_id}",
            access_token=credentials.access_token,
            json=body,
        )
        self._cache.invalidate(waba_id)
        return response

    async def delete(
        self, waba_id: str, *, name: str, hsm_id: str | None = None
    ) -> dict[str, Any]:
        """Borra una plantilla por nombre, o una versión concreta con ``hsm_id``.

        Sin ``hsm_id`` se borran **todas las variantes de idioma** con ese nombre.
        """
        credentials = await self._resolver.for_waba_id(waba_id)
        params: dict[str, Any] = {"name": str(name).strip()}
        if hsm_id:
            params["hsm_id"] = hsm_id
        response = await self._transport.request(
            "DELETE",
            f"/{waba_id}/message_templates",
            access_token=credentials.access_token,
            params=params,
        )
        self._cache.invalidate(waba_id)
        return response

    # -- Consulta ----------------------------------------------------------------

    async def list_all(
        self,
        waba_id: str,
        *,
        use_cache: bool = True,
        page_size: int = _DEFAULT_PAGE_SIZE,
        status: str | None = None,
        category: str | None = None,
    ) -> list[TemplateInfo]:
        """Lista las plantillas de la WABA, siguiendo la paginación por cursores.

        Meta pagina el listado: quedarse con la primera página deja fuera plantillas en
        cuentas con más de ``page_size``. El cache solo se usa cuando no hay filtros,
        para no servir un subconjunto filtrado como si fuera la lista completa.
        """
        cacheable = status is None and category is None
        if use_cache and cacheable:
            cached = self._cache.get(waba_id)
            if cached is not None:
                return cached

        credentials = await self._resolver.for_waba_id(waba_id)
        params: dict[str, Any] = {"limit": page_size}
        if status:
            params["status"] = status
        if category:
            params["category"] = category

        templates: list[TemplateInfo] = []
        after: str | None = None

        for _ in range(_MAX_PAGES):
            page_params = dict(params)
            if after:
                page_params["after"] = after
            response = await self._transport.request(
                "GET",
                f"/{waba_id}/message_templates",
                access_token=credentials.access_token,
                params=page_params,
            )
            data = response.get("data")
            if isinstance(data, list):
                templates.extend(
                    TemplateInfo.from_meta(i) for i in data if isinstance(i, dict)
                )

            next_cursor = _next_cursor(response)
            if not next_cursor or next_cursor == after:
                break
            after = next_cursor

        if cacheable:
            self._cache.set(waba_id, templates)
        return templates

    async def get(
        self, waba_id: str, name: str, *, language: str | None = None
    ) -> TemplateInfo | None:
        """Busca una plantilla por nombre, y opcionalmente por idioma.

        El nombre no es único por sí solo: una plantilla puede existir en varios
        idiomas. Sin ``language`` se devuelve la primera coincidencia.
        """
        for template in await self.list_all(waba_id):
            if template.name != name:
                continue
            if language is None or template.language == language:
                return template
        return None

    async def status(self, waba_id: str, name: str) -> str | None:
        """Estado de aprobación de una plantilla por nombre (``None`` si no existe)."""
        template = await self.get(waba_id, name)
        return template.status if template else None

    # -- Envío por la Marketing Messages API -------------------------------------

    async def send_marketing(
        self, payload: dict[str, Any], *, phone_number_id: str
    ) -> SendResult:
        """Envía un payload de marketing ya construido.

        Ojo al interpretar la respuesta: ``message_status`` puede venir como ``paused``
        o ``held_for_quality_assessment``, que significan aceptado pero **no entregado**.
        """
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        response = await self._transport.request(
            "POST",
            f"/{phone_number_id}/marketing_messages",
            access_token=credentials.access_token,
            json=payload,
            phone_number_id=phone_number_id,
        )
        return SendResult.from_response(response)

    async def send_marketing_template(
        self,
        *,
        phone_number_id: str,
        name: str,
        language_code: str,
        components: list[dict[str, Any]] | None = None,
        to: str | None = None,
        recipient: str | None = None,
        product_policy: str | None = None,
        message_activity_sharing: bool | None = None,
    ) -> SendResult:
        """Arma el payload de marketing y lo envía."""
        payload = builders.build_marketing_template(
            name=name,
            language_code=language_code,
            components=components,
            to=to,
            recipient=recipient,
            product_policy=product_policy,
            message_activity_sharing=message_activity_sharing,
        )
        return await self.send_marketing(payload, phone_number_id=phone_number_id)


def _next_cursor(response: dict[str, Any]) -> str | None:
    """Cursor ``after`` de la siguiente página, si Meta indicó que hay más.

    Se exige la presencia de ``paging.next``: Meta devuelve cursores en la última página
    también, y seguirlos sin comprobar ``next`` provoca una petición extra vacía por cada
    listado.
    """
    paging = response.get("paging")
    if not isinstance(paging, dict) or not paging.get("next"):
        return None
    cursors = paging.get("cursors")
    if not isinstance(cursors, dict):
        return None
    after = cursors.get("after")
    return after if isinstance(after, str) and after else None
