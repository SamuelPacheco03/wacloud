"""Mensajes que abren un WhatsApp Flow.

Un Flow es un formulario multipantalla que se ejecuta dentro de WhatsApp. El mensaje solo
lo lanza; el contenido lo define el Flow ya publicado en Meta.

Sobre ``flow_token``: es el dato con el que se correlaciona la respuesta. Meta avisa de
que *"the Flow response does not include the Flow ID"*, así que sin un token propio no hay
forma de saber a qué conversación pertenece un envío recibido. El valor por defecto de
Meta es la cadena ``"unused"``, que no sirve para correlacionar nada.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/flows
"""

from __future__ import annotations

from typing import Any

from wacloud.flows import FlowAction, FlowMode
from wacloud.limits import InteractiveLimits, ensure_max_length
from wacloud.messages.builders.interactive import interactive_message

__all__ = ["build_interactive_flow"]

#: Versión del protocolo de mensaje de Flow. Meta solo acepta "3".
_FLOW_MESSAGE_VERSION = "3"


def build_interactive_flow(
    to: str,
    body: str,
    cta: str,
    *,
    flow_token: str,
    flow_id: str | None = None,
    flow_name: str | None = None,
    flow_action: FlowAction | str = FlowAction.NAVIGATE,
    screen: str | None = None,
    data: dict[str, Any] | None = None,
    mode: FlowMode | str = FlowMode.PUBLISHED,
    header: dict[str, Any] | None = None,
    footer: str | None = None,
) -> dict[str, Any]:
    """Mensaje que abre un Flow.

    Hay que dar ``flow_id`` **o** ``flow_name``, no ambos.

    ``screen`` es la pantalla inicial y solo tiene sentido con ``flow_action=navigate``;
    con ``data_exchange`` la decide el endpoint del Flow.

    ``data`` son los datos iniciales de esa pantalla. Meta se contradice sobre su formato:
    la guía de Flows lo muestra como cadena JSON y la referencia de la Messages API como
    objeto anidado. Aquí se manda **objeto**, que es lo que declara su esquema. Si Meta
    lo rechaza en algún caso, serializarlo antes de pasarlo es la vuelta atrás.
    """
    provided = [v for v in (flow_id, flow_name) if v]
    if len(provided) != 1:
        raise ValueError("se requiere exactamente uno de 'flow_id' o 'flow_name'")

    clean_token = str(flow_token or "").strip()
    if not clean_token:
        raise ValueError(
            "flow_token es obligatorio: la respuesta del Flow no incluye el flow_id, "
            "así que es la única forma de correlacionarla"
        )

    clean_cta = str(cta or "").strip()
    if not clean_cta:
        raise ValueError("la etiqueta del botón (cta) es obligatoria")
    ensure_max_length(clean_cta, InteractiveLimits.FLOW_CTA, field="flow_cta")
    ensure_max_length(body, InteractiveLimits.BODY, field="interactive.body")

    try:
        flow_mode = FlowMode(mode)
    except ValueError as exc:
        valid = ", ".join(m.value for m in FlowMode)
        raise ValueError(f"mode debe ser uno de: {valid}; se recibió {mode!r}") from exc

    action = FlowAction(flow_action)
    if screen and action is not FlowAction.NAVIGATE:
        raise ValueError(
            "'screen' solo aplica con flow_action=navigate; con data_exchange la "
            "pantalla la decide el endpoint del Flow"
        )

    parameters: dict[str, Any] = {
        "flow_message_version": _FLOW_MESSAGE_VERSION,
        "flow_token": clean_token,
        "flow_cta": clean_cta,
        "flow_action": action.value,
        "mode": flow_mode.value,
    }
    if flow_id:
        parameters["flow_id"] = str(flow_id)
    else:
        parameters["flow_name"] = str(flow_name)

    payload: dict[str, Any] = {}
    if screen:
        payload["screen"] = screen
    if data:
        # Meta rechaza un ``data`` vacío, así que solo se incluye con contenido.
        payload["data"] = data
    if payload:
        parameters["flow_action_payload"] = payload

    interactive: dict[str, Any] = {
        "type": "flow",
        "body": {"text": body},
        "action": {"name": "flow", "parameters": parameters},
    }
    return interactive_message(to, interactive, header=header, footer=footer)
