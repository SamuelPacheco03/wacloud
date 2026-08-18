"""Plantillas: definición, creación, envío y gestión.

Dos mundos que Meta llama igual pero no lo son:

- **Crear** una plantilla: ``components`` + ``buttons`` describen su estructura, con
  ``example`` para cada variable. Se ensambla con ``definition.build_definition``.
- **Enviar** una plantilla aprobada: ``parameters`` aporta los valores concretos.
"""

from wacloud.templates import builders, buttons, components, parameters
from wacloud.templates.client import TemplatesClient
from wacloud.templates.definition import build_definition, validate_name
from wacloud.templates.enums import (
    ButtonType,
    FlowAction,
    FlowIcon,
    HeaderFormat,
    OtpType,
    ParameterFormat,
    TemplateCategory,
    TemplateStatus,
)
from wacloud.templates.placeholders import analyze, detect_format, find_placeholders

__all__ = [
    "TemplatesClient",
    "builders",
    "buttons",
    "components",
    "parameters",
    "build_definition",
    "validate_name",
    "analyze",
    "detect_format",
    "find_placeholders",
    "ButtonType",
    "FlowAction",
    "FlowIcon",
    "HeaderFormat",
    "OtpType",
    "ParameterFormat",
    "TemplateCategory",
    "TemplateStatus",
]
