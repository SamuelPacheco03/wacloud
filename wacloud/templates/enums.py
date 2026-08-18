"""Valores enumerados de la API de plantillas de Meta.

Se declaran como ``str, Enum`` para que sirvan tanto de constante tipada como de valor
serializable directamente en el JSON.

Nota sobre completitud: el enum de tipos de botón que publica Meta en la referencia de la
Graph API **está incompleto** (omite ``SPM``, ``COPY_CODE`` y ``ORDER_DETAILS``, que tienen
página de documentación propia y funcionan). Los que aparecen aquí son los verificados
contra documentación real, no solo contra ese enum.
"""

from __future__ import annotations

from enum import Enum

# Reexportados: los Flows no son un concepto de plantillas, pero el botón FLOW sí
# los usa, así que siguen accesibles desde aquí.
from wacloud.flows import FlowAction, FlowIcon, FlowMode

__all__ = [
    "MEDIA_HEADER_FORMATS",
    "OTP_TYPES_REQUIRING_APPS",
    "ButtonType",
    "FlowAction",
    "FlowIcon",
    "FlowMode",
    "HeaderFormat",
    "OtpType",
    "ParameterFormat",
    "TemplateCategory",
    "TemplateStatus",
]


class ParameterFormat(str, Enum):
    """Cómo se escriben las variables de la plantilla."""

    #: ``{{1}}``, ``{{2}}``… El orden del array de parámetros manda al enviar.
    POSITIONAL = "POSITIONAL"
    #: ``{{order_number}}``. Cada parámetro lleva su ``parameter_name`` al enviar.
    NAMED = "NAMED"


class TemplateCategory(str, Enum):
    """Categoría de la plantilla. Determina precio y reglas de aprobación.

    Meta recategoriza automáticamente una plantilla de ``UTILITY`` cuyo contenido suene a
    marketing, así que la categoría declarada no siempre es la final.
    """

    MARKETING = "MARKETING"
    UTILITY = "UTILITY"
    AUTHENTICATION = "AUTHENTICATION"


class TemplateStatus(str, Enum):
    """Estado de aprobación. ``ARCHIVED`` solo llega por webhook, no por el nodo."""

    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"
    IN_APPEAL = "IN_APPEAL"
    PENDING_DELETION = "PENDING_DELETION"
    DELETED = "DELETED"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"


class HeaderFormat(str, Enum):
    """Formato de la cabecera de una plantilla."""

    TEXT = "TEXT"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    DOCUMENT = "DOCUMENT"
    #: Sin ``example``: las coordenadas se pasan al enviar, no al crear.
    LOCATION = "LOCATION"
    #: Solo disponible en la Marketing Messages API. Máximo 3,5 MB.
    GIF = "GIF"


#: Cabeceras que exigen un ``header_handle`` de la Resumable Upload API al crear.
MEDIA_HEADER_FORMATS = frozenset(
    {HeaderFormat.IMAGE, HeaderFormat.VIDEO, HeaderFormat.DOCUMENT, HeaderFormat.GIF}
)


class ButtonType(str, Enum):
    """Tipos de botón de una plantilla."""

    QUICK_REPLY = "QUICK_REPLY"
    URL = "URL"
    PHONE_NUMBER = "PHONE_NUMBER"
    COPY_CODE = "COPY_CODE"
    OTP = "OTP"
    FLOW = "FLOW"
    CATALOG = "CATALOG"
    #: Multi-Product Message.
    MPM = "MPM"
    #: Single-Product Message.
    SPM = "SPM"
    ORDER_DETAILS = "ORDER_DETAILS"
    VOICE_CALL = "VOICE_CALL"


class OtpType(str, Enum):
    """Variante del botón OTP de una plantilla de autenticación."""

    #: El usuario copia el código y lo pega en la app.
    COPY_CODE = "COPY_CODE"
    #: Un toque rellena el código en la app. Exige ``supported_apps``.
    ONE_TAP = "ONE_TAP"
    #: El código se rellena sin interacción. Exige ``supported_apps``.
    ZERO_TAP = "ZERO_TAP"


#: Variantes de OTP que exigen declarar las apps que pueden recibir el código.
OTP_TYPES_REQUIRING_APPS = frozenset({OtpType.ONE_TAP, OtpType.ZERO_TAP})
