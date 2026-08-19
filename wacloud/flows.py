"""Valores compartidos de WhatsApp Flows.

Viven en la raíz del paquete porque los Flows aparecen en dos sitios que no dependen
entre sí: el botón ``FLOW`` de una plantilla y el mensaje interactivo de tipo ``flow``.
Colgarlos de ``templates`` obligaría a ``messages`` a importar de ``templates``, que
invierte el sentido de las capas.
"""

from __future__ import annotations

from enum import Enum


class FlowAction(str, Enum):
    """Qué hace el Flow al abrirse."""

    #: Abre una pantalla concreta del Flow.
    NAVIGATE = "navigate"
    #: Consulta al endpoint del Flow, que decide qué mostrar.
    DATA_EXCHANGE = "data_exchange"


class FlowIcon(str, Enum):
    """Icono del botón de Flow en una plantilla."""

    DOCUMENT = "DOCUMENT"
    PROMOTION = "PROMOTION"
    REVIEW = "REVIEW"


class FlowMode(str, Enum):
    """En qué estado del Flow se abre.

    ``DRAFT`` sirve para probar un Flow sin publicar y solo funciona para los
    administradores de la cuenta.
    """

    DRAFT = "draft"
    PUBLISHED = "published"
