"""Gestión del número: estado, registro, verificación y perfil de negocio.

Administración de la línea, no mensajería. Usa la Business Management API, con su propio
límite de 200 peticiones por hora y WABA (5.000 si tiene un número registrado).
"""

from wacloud.numbers.client import NumbersClient
from wacloud.numbers.enums import (
    DATA_LOCALIZATION_REGIONS,
    AccountMode,
    BusinessVertical,
    CodeMethod,
    CodeVerificationStatus,
    NameStatus,
    NumberStatus,
    QualityRating,
)
from wacloud.numbers.models import BusinessProfile, PhoneNumberInfo

__all__ = [
    "NumbersClient",
    "PhoneNumberInfo",
    "BusinessProfile",
    "QualityRating",
    "NumberStatus",
    "CodeVerificationStatus",
    "AccountMode",
    "NameStatus",
    "CodeMethod",
    "BusinessVertical",
    "DATA_LOCALIZATION_REGIONS",
]
