"""Clasificación de los códigos de error de la Cloud API de Meta.

Meta es explícita al respecto: *"Build your app's error handling around error codes
instead of subcodes or HTTP response status codes"*. El mismo HTTP 400 puede ser un
fallo permanente de validación o algo que se resuelve solo en 24 horas, así que
ramificar por status es insuficiente.

Este módulo es una tabla de datos, sin lógica de red. La decisión que expone es una
sola: dado un código de Meta, ¿se puede reintentar y cuánto hay que esperar como
mínimo?

Referencia: https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes
"""

from __future__ import annotations

from dataclasses import dataclass

#: Un día en segundos, para las esperas que Meta impone por política.
_ONE_DAY = 86_400.0

#: Status HTTP relevantes para clasificar. Nombrarlos evita literales sueltos en
#: las comparaciones y deja claro qué significa cada rango.
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR_FLOOR = 500
HTTP_SERVER_ERROR_CEIL = 600


@dataclass(frozen=True)
class RetryRule:
    """Qué hacer ante un código concreto de Meta.

    ``min_wait_seconds`` es el suelo que impone Meta, no una sugerencia: para
    ``131049`` reintentar antes de tiempo *añade* otras 24 horas de penalización.
    """

    retryable: bool
    min_wait_seconds: float = 0.0
    reason: str = ""


#: Reintentar aquí es contraproducente: el resultado no va a cambiar y en algunos
#: casos empeora la reputación del número.
_NEVER_RETRY: dict[int, str] = {
    130403: "el negocio ha bloqueado a este usuario en WhatsApp",
    131050: "el usuario optó por no recibir mensajes de marketing",
    131026: "el destinatario no es alcanzable (no usa WhatsApp o no aceptó los ToS)",
    131021: "emisor y destinatario son el mismo número",
    131047: "pasaron más de 24 h desde la última respuesta: hay que usar una plantilla",
    131051: "tipo de mensaje no soportado",
    131052: "no se pudo descargar el medio del usuario o excede el tamaño máximo",
    131053: "no se pudo subir el medio (el MIME declarado no coincide)",
    131063: "el marketing está desactivado en la configuración de Cloud API",
    132000: "el número de variables no coincide con el de la plantilla",
    132001: "la plantilla no existe en ese idioma o no está aprobada",
    132005: "el texto traducido de la plantilla es demasiado largo",
    132007: "el contenido de la plantilla viola la política de Meta",
    132012: "los valores de las variables están mal formateados",
    132015: "la plantilla está pausada por baja calidad",
    132016: "la plantilla está deshabilitada permanentemente",
    133005: "PIN de verificación en dos pasos incorrecto",
    133010: "el número no está registrado",
    134100: "la Marketing Messages API solo acepta plantillas de marketing",
}

#: Códigos que Meta documenta como transitorios. El valor es la espera mínima.
_RETRYABLE: dict[int, tuple[float, str]] = {
    2: (0.0, "fallo temporal de Meta (caída o sobrecarga)"),
    4: (0.0, "la app alcanzó su límite de llamadas"),
    80007: (0.0, "la WABA alcanzó su rate limit"),
    80008: (0.0, "rate limit de la Business Management API"),
    130429: (0.0, "se alcanzó el throughput de mensajes de Cloud API"),
    131000: (0.0, "error desconocido de Meta; se puede reintentar"),
    131016: (0.0, "servicio temporalmente no disponible"),
    131056: (6.0, "pair rate limit: 1 mensaje cada 6 s al mismo usuario"),
    131057: (0.0, "cuenta en mantenimiento por un upgrade de throughput (hasta 1 min)"),
    133004: (0.0, "servidor temporalmente no disponible"),
    133008: (0.0, "demasiados intentos de PIN"),
    133015: (300.0, "número recién borrado: Meta pide esperar 5 minutos"),
    133016: (0.0, "límite de intentos de registro/deregistro"),
    134101: (60.0, "la plantilla aún se está sincronizando (hasta 10 min)"),
    2494100: (0.0, "cuenta en modo mantenimiento"),
}

#: Esperas largas impuestas por política. Son reintentables en el sentido de que el
#: mensaje acabará pasando, pero no dentro del ciclo de vida de una petición.
_POLICY_WAIT: dict[int, tuple[float, str]] = {
    131049: (
        _ONE_DAY,
        "límite de marketing por usuario: hay que esperar 24 h "
        "(reintentar antes añade otras 24 h)",
    ),
    131048: (
        _ONE_DAY,
        "restricción por mensajes previos marcados como spam",
    ),
}


def rule_for_code(code: int | None) -> RetryRule | None:
    """Regla de reintento para un código de Meta, o ``None`` si no está catalogado.

    Devolver ``None`` es información útil: significa "no sé", y el llamador debe
    caer en la heurística por status HTTP en vez de asumir nada.
    """
    if code is None:
        return None

    reason = _NEVER_RETRY.get(code)
    if reason is not None:
        return RetryRule(retryable=False, reason=reason)

    policy = _POLICY_WAIT.get(code)
    if policy is not None:
        wait, why = policy
        return RetryRule(retryable=True, min_wait_seconds=wait, reason=why)

    transient = _RETRYABLE.get(code)
    if transient is not None:
        wait, why = transient
        return RetryRule(retryable=True, min_wait_seconds=wait, reason=why)

    return None


def rule_for_status(status_code: int) -> RetryRule:
    """Heurística de respaldo cuando Meta no envió un código reconocible."""
    if status_code == HTTP_TOO_MANY_REQUESTS:
        return RetryRule(retryable=True, reason="HTTP 429 (rate limit)")
    if HTTP_SERVER_ERROR_FLOOR <= status_code < HTTP_SERVER_ERROR_CEIL:
        return RetryRule(retryable=True, reason=f"HTTP {status_code} (error de Meta)")
    return RetryRule(retryable=False, reason=f"HTTP {status_code}")
