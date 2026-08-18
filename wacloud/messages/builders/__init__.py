"""Constructores de payloads para ``POST /{phone_number_id}/messages``.

Funciones puras: reciben datos simples y devuelven el ``dict`` listo para enviar. No
hacen red ni resuelven credenciales, así que se testean sin mocks.

Criterio de validación: **estricto al construir, permisivo al parsear**. Si un valor
excede un límite de Meta se lanza ``ValueError`` en vez de recortarlo. Recortar en
silencio hace que el destinatario reciba algo distinto de lo que el host quiso enviar y
el fallo no aparece en ningún log.

El paquete está partido por familia de mensaje; este módulo reexporta todo, así que
``from wacloud.messages import builders`` sigue dando acceso a la misma API.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/messages
"""

from wacloud.flows import FlowMode
from wacloud.messages.builders.contacts import (
    build_contacts,
    contact,
    contact_address,
    contact_email,
    contact_name,
    contact_org,
    contact_phone,
    contact_url,
)
from wacloud.messages.builders.context import as_reply
from wacloud.messages.builders.interactive import (
    build_interactive_buttons,
    build_interactive_cta_url,
    interactive_message,
)
from wacloud.messages.builders.interactive_flow import build_interactive_flow
from wacloud.messages.builders.interactive_list import (
    build_interactive_list,
    list_row,
    list_section,
)
from wacloud.messages.builders.location import build_location
from wacloud.messages.builders.media import (
    build_audio,
    build_document,
    build_image,
    build_sticker,
    build_video,
    media_object,
)
from wacloud.messages.builders.reactions import build_reaction, build_remove_reaction
from wacloud.messages.builders.status import build_mark_read
from wacloud.messages.builders.template import build_template
from wacloud.messages.builders.text import build_text
from wacloud.recipient import digits_only, recipient_block

__all__ = [
    # Texto
    "build_text",
    # Medios
    "build_image",
    "build_document",
    "build_video",
    "build_audio",
    "build_sticker",
    "media_object",
    # Interactivos
    "build_interactive_buttons",
    "build_interactive_cta_url",
    "build_interactive_list",
    "list_row",
    "list_section",
    "build_interactive_flow",
    "FlowMode",
    "interactive_message",
    # Ubicación
    "build_location",
    # Contactos
    "build_contacts",
    "contact",
    "contact_name",
    "contact_phone",
    "contact_email",
    "contact_url",
    "contact_address",
    "contact_org",
    # Reacciones
    "build_reaction",
    "build_remove_reaction",
    # Plantillas
    "build_template",
    # Estado y modificadores
    "build_mark_read",
    "as_reply",
    # Destinatario
    "digits_only",
    "recipient_block",
]
