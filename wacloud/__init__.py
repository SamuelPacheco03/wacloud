"""wacloud — cliente stateless para la WhatsApp Cloud API de Meta."""
from wacloud.config import DEFAULT_CONFIG, GraphConfig
from wacloud.credentials import (
    CredentialResolver,
    StaticCredentialResolver,
    WaCredentials,
)
from wacloud.errors import (
    WaCloudError,
    WaInvalidRequest,
    WaRateLimited,
    WaServerError,
    WaTransportError,
)
from wacloud.media import StorageBackend, StoredMedia
from wacloud.messages import MessagesClient, builders
from wacloud.models import BatchSendResult, SendResult, TemplateInfo
from wacloud.templates import TemplatesClient
from wacloud.transport import Transport
from wacloud.webhook import (
    WebhookEvents,
    WebhookInboundMessage,
    WebhookStatus,
    first_phone_number_id,
    parse_webhook,
    verify_signature,
)

__version__ = "0.1.0"

__all__ = [
    "GraphConfig",
    "DEFAULT_CONFIG",
    "Transport",
    "WaCredentials",
    "CredentialResolver",
    "StaticCredentialResolver",
    "StorageBackend",
    "StoredMedia",
    "MessagesClient",
    "TemplatesClient",
    "builders",
    "SendResult",
    "BatchSendResult",
    "TemplateInfo",
    "verify_signature",
    "parse_webhook",
    "first_phone_number_id",
    "WebhookEvents",
    "WebhookInboundMessage",
    "WebhookStatus",
    "WaCloudError",
    "WaTransportError",
    "WaInvalidRequest",
    "WaRateLimited",
    "WaServerError",
]
