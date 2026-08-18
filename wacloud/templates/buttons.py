"""Constructores de botones para la **creación** de plantillas.

Ojo con la distinción, que Meta no ayuda a ver: estos botones describen la plantilla que
se registra en la WABA (``POST /{waba_id}/message_templates``). Los parámetros que se
mandan **al enviar** una plantilla ya aprobada están en ``wacloud.templates.parameters``.

Funciones puras que devuelven el ``dict`` de un botón. La validación de cuántos botones
de cada tipo caben junta vive en ``components.buttons``, que es quien ve el conjunto.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/components
"""

from __future__ import annotations

from typing import Any

from wacloud.limits import TemplateLimits, ensure_max_length
from wacloud.templates.enums import ButtonType, FlowAction, FlowIcon, OtpType
from wacloud.templates.placeholders import find_placeholders

__all__ = [
    "call_permission_request",
    "catalog",
    "copy_code",
    "flow",
    "mpm",
    "order_details",
    "otp",
    "phone_number",
    "quick_reply",
    "spm",
    "url",
    "voice_call",
]

#: Rango que acepta Meta para el TTL de un botón de llamada de voz, en minutos.
_VOICE_CALL_TTL_RANGE = (1440, 43200)


def _label(text: str, *, maximum: int = TemplateLimits.BUTTON_TEXT) -> str:
    clean = str(text or "").strip()
    if not clean:
        raise ValueError("el texto del botón es obligatorio")
    return ensure_max_length(clean, maximum, field="button.text")


def quick_reply(text: str) -> dict[str, Any]:
    """Botón de respuesta rápida. Al pulsarlo llega un mensaje ``type=button``."""
    return {"type": ButtonType.QUICK_REPLY.value, "text": _label(text)}


def url(text: str, link: str, *, example: str | None = None) -> dict[str, Any]:
    """Botón que abre una URL, opcionalmente con una variable al final.

    Meta admite **una sola variable** y **solo al final** de la URL: sirve para el sufijo
    dinámico (``/pedidos/{{1}}``), no para construir la URL entera. Si hay variable,
    ``example`` es obligatorio.

    El valor que se manda al enviar debe ir **percent-encoded**: Meta no lo escapa.
    """
    clean_url = str(link or "").strip()
    if not clean_url:
        raise ValueError("la URL del botón es obligatoria")
    ensure_max_length(clean_url, TemplateLimits.URL, field="button.url")

    placeholders = find_placeholders(clean_url)
    button: dict[str, Any] = {
        "type": ButtonType.URL.value,
        "text": _label(text),
        "url": clean_url,
    }

    if not placeholders:
        if example is not None:
            raise ValueError("la URL no tiene variables, sobra 'example'")
        return button

    if len(placeholders) > 1:
        raise ValueError(f"la URL admite una sola variable, tiene {len(placeholders)}")
    if not clean_url.endswith("}}"):
        raise ValueError("la variable de la URL debe ir al final")
    if example is None:
        raise ValueError("la URL tiene una variable: 'example' es obligatorio")

    # El ejemplo va como array plano y directamente en el botón, no envuelto en
    # un objeto ``example`` como en los componentes de texto.
    button["example"] = [str(example)]
    return button


def phone_number(text: str, number: str) -> dict[str, Any]:
    """Botón de llamada. El número va en formato internacional."""
    clean = str(number or "").strip()
    if not clean:
        raise ValueError("el número de teléfono es obligatorio")
    ensure_max_length(clean, TemplateLimits.PHONE_NUMBER, field="button.phone_number")
    return {
        "type": ButtonType.PHONE_NUMBER.value,
        "text": _label(text),
        "phone_number": clean,
    }


def copy_code(example: str) -> dict[str, Any]:
    """Botón que copia un código de descuento al portapapeles.

    No lleva ``text``: la etiqueta la pone WhatsApp. El ``example`` va como **cadena
    suelta**, no como array, a diferencia del resto de ejemplos.
    """
    clean = str(example or "").strip()
    if not clean:
        raise ValueError("el código de ejemplo es obligatorio")
    ensure_max_length(clean, TemplateLimits.COPY_CODE_EXAMPLE, field="button.example")
    return {"type": ButtonType.COPY_CODE.value, "example": clean}


def otp(
    otp_type: OtpType | str,
    *,
    supported_apps: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Botón OTP de una plantilla de autenticación.

    No lleva ``text`` ni ``autofill_text``: Meta genera las etiquetas y el cuerpo de las
    plantillas de autenticación, y **rechaza el payload si se envían**.

    ``ONE_TAP`` y ``ZERO_TAP`` exigen ``supported_apps``: la lista de apps que pueden
    recibir el código, cada una con ``package_name`` y ``signature_hash``.
    """
    kind = OtpType(otp_type)
    button: dict[str, Any] = {
        "type": ButtonType.OTP.value,
        "otp_type": kind.value,
    }

    if kind is OtpType.COPY_CODE:
        if supported_apps:
            raise ValueError("otp_type=COPY_CODE no admite 'supported_apps'")
        return button

    if not supported_apps:
        raise ValueError(f"otp_type={kind.value} exige 'supported_apps'")
    for app in supported_apps:
        if not app.get("package_name") or not app.get("signature_hash"):
            raise ValueError(
                "cada app de 'supported_apps' necesita 'package_name' y 'signature_hash'"
            )
    button["supported_apps"] = list(supported_apps)
    return button


def flow(
    text: str,
    *,
    flow_id: str | None = None,
    flow_name: str | None = None,
    flow_json: str | None = None,
    flow_action: FlowAction | str = FlowAction.NAVIGATE,
    navigate_screen: str | None = None,
    icon: FlowIcon | str | None = None,
) -> dict[str, Any]:
    """Botón que abre un WhatsApp Flow.

    Hay que dar **exactamente uno** de ``flow_id``, ``flow_name`` o ``flow_json``. La
    etiqueta admite 20 caracteres, no 25 como el resto, y no acepta emoji.

    ``navigate_screen`` lo valida Meta **en el envío, no en la creación**: un valor
    equivocado aquí se aprueba y falla después.
    """
    provided = [v for v in (flow_id, flow_name, flow_json) if v]
    if len(provided) != 1:
        raise ValueError("se requiere exactamente uno de 'flow_id', 'flow_name' o 'flow_json'")

    button: dict[str, Any] = {
        "type": ButtonType.FLOW.value,
        "text": _label(text, maximum=TemplateLimits.FLOW_BUTTON_TEXT),
        "flow_action": FlowAction(flow_action).value,
    }
    if flow_id:
        button["flow_id"] = str(flow_id)
    elif flow_name:
        button["flow_name"] = str(flow_name)
    else:
        button["flow_json"] = flow_json

    if navigate_screen:
        button["navigate_screen"] = navigate_screen
    if icon is not None:
        button["icon"] = FlowIcon(icon).value
    return button


def catalog(text: str = "View catalog") -> dict[str, Any]:
    """Botón que abre el catálogo del negocio."""
    return {"type": ButtonType.CATALOG.value, "text": _label(text)}


def mpm(text: str = "View items") -> dict[str, Any]:
    """Botón de mensaje multi-producto."""
    return {"type": ButtonType.MPM.value, "text": _label(text)}


def spm(text: str = "View") -> dict[str, Any]:
    """Botón de mensaje de producto único."""
    return {"type": ButtonType.SPM.value, "text": _label(text)}


def order_details(text: str) -> dict[str, Any]:
    """Botón de detalles del pedido, para el flujo de pago."""
    return {"type": ButtonType.ORDER_DETAILS.value, "text": _label(text)}


def voice_call(text: str, *, ttl_minutes: int | None = None) -> dict[str, Any]:
    """Botón de llamada de voz por WhatsApp.

    ``ttl_minutes`` acepta entre 1440 (un día) y 43200 (30 días).
    """
    button: dict[str, Any] = {
        "type": ButtonType.VOICE_CALL.value,
        "text": _label(text, maximum=TemplateLimits.VOICE_CALL_BUTTON_TEXT),
    }
    if ttl_minutes is not None:
        low, high = _VOICE_CALL_TTL_RANGE
        if not low <= ttl_minutes <= high:
            raise ValueError(f"ttl_minutes debe estar entre {low} y {high}, no {ttl_minutes}")
        button["ttl_minutes"] = ttl_minutes
    return button


def call_permission_request(text: str) -> dict[str, Any]:
    """Botón que pide permiso al usuario para llamarle.

    Meta lo lista en el enum de la Graph API pero no publica documentación propia: la
    forma es la mínima común (tipo + etiqueta). Verificar antes de usarlo en producción.
    """
    return {"type": "REQUEST_CALL_PERMISSION", "text": _label(text)}
