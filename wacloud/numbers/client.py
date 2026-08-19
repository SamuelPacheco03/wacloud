"""Gestión del número: estado, registro, verificación y perfil de negocio.

Cubre la administración del número en sí, no la mensajería. Todo lo de aquí usa la Business
Management API, que tiene su propio límite: **200 peticiones por hora y WABA**, o 5.000 si
la WABA tiene al menos un número registrado. Pasarse devuelve el código ``80008``.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/phone-numbers
"""

from __future__ import annotations

import re
from typing import Any

from wacloud.credentials import CredentialResolver
from wacloud.numbers.enums import (
    DATA_LOCALIZATION_REGIONS,
    BusinessVertical,
    CodeMethod,
)
from wacloud.numbers.models import BusinessProfile, PhoneNumberInfo
from wacloud.transport import Transport

#: Campos que se piden por defecto al consultar un número. Meta devuelve un subconjunto
#: mínimo si no se especifican, así que se enumeran para obtener siempre lo mismo.
_NUMBER_FIELDS = (
    "id",
    "display_phone_number",
    "verified_name",
    "quality_rating",
    "status",
    "code_verification_status",
    "name_status",
    "account_mode",
    "is_official_business_account",
    "whatsapp_business_manager_messaging_limit",
)

#: Campos del perfil de negocio. Meta no los devuelve si no se piden explícitamente.
_PROFILE_FIELDS = (
    "about",
    "address",
    "description",
    "email",
    "profile_picture_url",
    "websites",
    "vertical",
)

#: El PIN de verificación en dos pasos son exactamente seis dígitos.
_PIN = re.compile(r"^\d{6}$")

#: Tope de páginas al listar números, por si un cursor no avanzara.
_MAX_PAGES = 20


class NumbersClient:
    """Administración de los números de una WABA."""

    def __init__(self, transport: Transport, resolver: CredentialResolver) -> None:
        self._transport = transport
        self._resolver = resolver

    # -- Consulta ----------------------------------------------------------------

    async def get(self, phone_number_id: str) -> PhoneNumberInfo:
        """Estado y metadatos de un número.

        Incluye la calidad de la línea y el límite de mensajería, que es lo que hay que
        vigilar para saber si un número está en riesgo de ser restringido.
        """
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        response = await self._transport.request(
            "GET",
            f"/{phone_number_id}",
            access_token=credentials.access_token,
            params={"fields": ",".join(_NUMBER_FIELDS)},
            phone_number_id=phone_number_id,
        )
        return PhoneNumberInfo.from_meta(response)

    async def list_all(self, waba_id: str, *, page_size: int = 50) -> list[PhoneNumberInfo]:
        """Todos los números de la WABA, siguiendo la paginación por cursores."""
        credentials = await self._resolver.for_waba_id(waba_id)
        numbers: list[PhoneNumberInfo] = []
        after: str | None = None

        for _ in range(_MAX_PAGES):
            params: dict[str, Any] = {
                "limit": page_size,
                "fields": ",".join(_NUMBER_FIELDS),
            }
            if after:
                params["after"] = after
            response = await self._transport.request(
                "GET",
                f"/{waba_id}/phone_numbers",
                access_token=credentials.access_token,
                params=params,
            )
            data = response.get("data")
            if isinstance(data, list):
                numbers.extend(
                    PhoneNumberInfo.from_meta(i) for i in data if isinstance(i, dict)
                )

            next_cursor = _next_cursor(response)
            if not next_cursor or next_cursor == after:
                break
            after = next_cursor

        return numbers

    # -- Registro y verificación -------------------------------------------------

    async def register(
        self,
        phone_number_id: str,
        *,
        pin: str,
        data_localization_region: str | None = None,
    ) -> bool:
        """Registra el número en la Cloud API para poder enviar y recibir.

        ``pin`` es el de verificación en dos pasos: seis dígitos. Si el número nunca tuvo
        uno, hay que fijarlo antes con ``set_two_step_pin``.

        ``data_localization_region`` fija dónde se almacenan los datos en reposo; solo
        admite las regiones que Meta habilita.

        Límite: **10 registros o bajas por número en 72 horas** (código ``133016``).
        """
        body: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "pin": _validated_pin(pin),
        }
        if data_localization_region:
            region = str(data_localization_region).strip().upper()
            if region not in DATA_LOCALIZATION_REGIONS:
                raise ValueError(
                    f"{region!r} no es una región de localización admitida; "
                    f"use una de {sorted(DATA_LOCALIZATION_REGIONS)}"
                )
            body["data_localization_region"] = region

        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        response = await self._transport.request(
            "POST",
            f"/{phone_number_id}/register",
            access_token=credentials.access_token,
            json=body,
            phone_number_id=phone_number_id,
        )
        return bool(response.get("success", False))

    async def deregister(self, phone_number_id: str) -> bool:
        """Da de baja el número de la Cloud API.

        Cuenta para el mismo límite de 10 operaciones por 72 horas que el registro.
        """
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        response = await self._transport.request(
            "POST",
            f"/{phone_number_id}/deregister",
            access_token=credentials.access_token,
            json={"messaging_product": "whatsapp"},
            phone_number_id=phone_number_id,
        )
        return bool(response.get("success", False))

    async def set_two_step_pin(self, phone_number_id: str, pin: str) -> bool:
        """Fija o cambia el PIN de verificación en dos pasos (seis dígitos)."""
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        response = await self._transport.request(
            "POST",
            f"/{phone_number_id}",
            access_token=credentials.access_token,
            json={"pin": _validated_pin(pin)},
            phone_number_id=phone_number_id,
        )
        return bool(response.get("success", False))

    async def request_verification_code(
        self,
        phone_number_id: str,
        *,
        method: CodeMethod | str = CodeMethod.SMS,
        language: str = "es",
    ) -> bool:
        """Pide a Meta que envíe el código de verificación por SMS o llamada.

        Si el número ya está verificado, Meta responde HTTP 400 con el código ``136024``.
        Conviene comprobar antes ``get(...).is_verified`` para no gastar un intento.
        """
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        response = await self._transport.request(
            "POST",
            f"/{phone_number_id}/request_code",
            access_token=credentials.access_token,
            params={
                "code_method": CodeMethod(method).value,
                "language": language,
            },
            phone_number_id=phone_number_id,
        )
        return bool(response.get("success", False))

    async def verify_code(self, phone_number_id: str, code: str) -> bool:
        """Confirma el código recibido por SMS o llamada."""
        clean = str(code or "").strip()
        if not clean:
            raise ValueError("el código de verificación es obligatorio")
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        response = await self._transport.request(
            "POST",
            f"/{phone_number_id}/verify_code",
            access_token=credentials.access_token,
            params={"code": clean},
            phone_number_id=phone_number_id,
        )
        return bool(response.get("success", False))

    # -- Perfil de negocio -------------------------------------------------------

    async def get_profile(self, phone_number_id: str) -> BusinessProfile:
        """Perfil público del número."""
        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        response = await self._transport.request(
            "GET",
            f"/{phone_number_id}/whatsapp_business_profile",
            access_token=credentials.access_token,
            params={"fields": ",".join(_PROFILE_FIELDS)},
            phone_number_id=phone_number_id,
        )
        return BusinessProfile.from_meta(response)

    async def update_profile(
        self,
        phone_number_id: str,
        *,
        about: str | None = None,
        address: str | None = None,
        description: str | None = None,
        email: str | None = None,
        vertical: BusinessVertical | str | None = None,
        websites: list[str] | None = None,
        profile_picture_handle: str | None = None,
    ) -> bool:
        """Actualiza el perfil público. Solo se envían los campos indicados.

        ``profile_picture_handle`` sale de la Resumable Upload API
        (``wacloud.media.upload_resumable``), no de la Media API: para escribir la foto se
        usa un *handle*, aunque al leerla Meta devuelva ``profile_picture_url``.

        Aviso sobre longitudes: Meta **no publica hoy los límites de caracteres** de estos
        campos —la página que los tenía devuelve un error del lado de Meta— y los valores
        que circulan vienen de terceros. Por eso aquí no se validan: rechazar en local con
        un número inventado sería peor que dejar que responda Meta.
        """
        body: dict[str, Any] = {"messaging_product": "whatsapp"}
        optional = {
            "about": about,
            "address": address,
            "description": description,
            "email": email,
            "profile_picture_handle": profile_picture_handle,
        }
        body.update({k: v for k, v in optional.items() if v is not None})

        if vertical is not None:
            body["vertical"] = BusinessVertical(vertical).value
        if websites is not None:
            body["websites"] = list(websites)

        if len(body) == 1:
            raise ValueError("no se indicó ningún campo del perfil a actualizar")

        credentials = await self._resolver.for_phone_number_id(phone_number_id)
        response = await self._transport.request(
            "POST",
            f"/{phone_number_id}/whatsapp_business_profile",
            access_token=credentials.access_token,
            json=body,
            phone_number_id=phone_number_id,
        )
        return bool(response.get("success", False))


def _validated_pin(pin: str) -> str:
    clean = str(pin or "").strip()
    if not _PIN.match(clean):
        raise ValueError("el PIN de verificación en dos pasos son seis dígitos")
    return clean


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
