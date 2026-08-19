"""Valores enumerados de la gestión del número.

Se exponen como constantes para comparar, **no** para convertir la respuesta de Meta.
La razón: las dos generaciones de documentación de Meta discrepan en la ortografía de
varios de estos valores (``NOT_VERIFIED`` frente a ``UNVERIFIED``, ``UNCONNECTED`` frente
a ``DISCONNECTED``), así que forzar la respuesta a un enum haría reventar la librería ante
un valor que Meta considera válido. Los modelos guardan la cadena tal cual llega y estas
constantes sirven para compararla.
"""

from __future__ import annotations

from enum import Enum


class QualityRating(str, Enum):
    """Calidad de la línea según la reacción de los usuarios."""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    #: Sin datos suficientes todavía.
    NA = "NA"
    UNKNOWN = "UNKNOWN"


class NumberStatus(str, Enum):
    """Estado de conexión del número.

    Meta documenta ``UNCONNECTED`` en unas páginas y ``DISCONNECTED`` en otras: se
    incluyen ambos porque no está claro cuál emite realmente la API.
    """

    CONNECTED = "CONNECTED"
    UNCONNECTED = "UNCONNECTED"
    DISCONNECTED = "DISCONNECTED"
    FLAGGED = "FLAGGED"
    RESTRICTED = "RESTRICTED"
    UNKNOWN = "UNKNOWN"


class CodeVerificationStatus(str, Enum):
    """Si el número superó la verificación por código.

    Igual que arriba: Meta usa ``NOT_VERIFIED`` y ``UNVERIFIED`` en páginas distintas.
    """

    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    EXPIRED = "EXPIRED"


class AccountMode(str, Enum):
    """``SANDBOX`` limita a destinatarios de prueba; ``LIVE`` es producción."""

    SANDBOX = "SANDBOX"
    LIVE = "LIVE"


class NameStatus(str, Enum):
    """Estado de revisión del nombre visible del negocio."""

    APPROVED = "APPROVED"
    AVAILABLE_WITHOUT_REVIEW = "AVAILABLE_WITHOUT_REVIEW"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    PENDING_REVIEW = "PENDING_REVIEW"
    NONE = "NONE"


class CodeMethod(str, Enum):
    """Por dónde enviar el código de verificación."""

    SMS = "SMS"
    VOICE = "VOICE"


class BusinessVertical(str, Enum):
    """Sector del negocio, para el perfil público."""

    UNDEFINED = "UNDEFINED"
    OTHER = "OTHER"
    AUTO = "AUTO"
    BEAUTY = "BEAUTY"
    APPAREL = "APPAREL"
    EDU = "EDU"
    ENTERTAIN = "ENTERTAIN"
    EVENT_PLAN = "EVENT_PLAN"
    FINANCE = "FINANCE"
    GROCERY = "GROCERY"
    GOVT = "GOVT"
    HOTEL = "HOTEL"
    HEALTH = "HEALTH"
    NONPROFIT = "NONPROFIT"
    PROF_SERVICES = "PROF_SERVICES"
    RETAIL = "RETAIL"
    TRAVEL = "TRAVEL"
    RESTAURANT = "RESTAURANT"
    NOT_A_BIZ = "NOT_A_BIZ"
    ALCOHOL = "ALCOHOL"
    ONLINE_GAMBLING = "ONLINE_GAMBLING"
    PHYSICAL_GAMBLING = "PHYSICAL_GAMBLING"
    OTC_DRUGS = "OTC_DRUGS"
    MATRIMONY_SERVICE = "MATRIMONY_SERVICE"


#: Regiones donde Meta admite alojar los datos del número (ISO-3166 alpha-2).
DATA_LOCALIZATION_REGIONS = frozenset(
    {
        # APAC
        "AU",
        "ID",
        "IN",
        "JP",
        "SG",
        "KR",
        # Europa
        "DE",
        "CH",
        "GB",
        # Latinoamérica
        "BR",
        # Oriente Medio y África
        "BH",
        "ZA",
        "AE",
        # Norteamérica
        "CA",
    }
)
