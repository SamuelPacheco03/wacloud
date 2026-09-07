"""wacloud — cliente stateless para la WhatsApp Cloud API de Meta."""

from wacloud.config import DEFAULT_API_VERSION, DEFAULT_CONFIG, GraphConfig
from wacloud.credentials import (
    CredentialResolver,
    StaticCredentialResolver,
    WaCredentials,
)
from wacloud.error_codes import RetryRule, rule_for_code
from wacloud.errors import (
    MetaError,
    WaCloudError,
    WaInvalidRequest,
    WaRateLimited,
    WaServerError,
    WaTransportError,
    error_from_response,
)
from wacloud.flows import FlowAction, FlowIcon, FlowMode
from wacloud.media import (
    StorageBackend,
    StoredMedia,
    delete_media,
    get_media_metadata,
    upload_media,
    upload_resumable,
)
from wacloud.messages import MessagesClient, builders
from wacloud.models import BatchSendResult, SendResult, TemplateInfo
from wacloud.numbers import (
    BlockedUsersClient,
    BlockResult,
    BusinessProfile,
    BusinessVertical,
    CodeMethod,
    NumbersClient,
    PhoneNumberInfo,
    QualityRating,
)
from wacloud.oauth import OAuthClient
from wacloud.recipient import (
    digits_only,
    is_user_id,
    normalize_recipient,
    recipient_block,
)
from wacloud.retry import DEFAULT_RETRY_POLICY, NO_RETRY_POLICY, RetryPolicy
from wacloud.templates import (
    ButtonType,
    HeaderFormat,
    OtpType,
    ParameterFormat,
    TemplateCategory,
    TemplatesClient,
    TemplateStatus,
    build_definition,
    buttons,
    components,
    parameters,
)
from wacloud.transport import Transport
from wacloud.waba import BusinessToken, SubscribedApp, WabaClient, WabaInfo
from wacloud.webhook import (
    InboundContactCard,
    WebhookDiscarded,
    WebhookEvents,
    WebhookInboundMessage,
    WebhookStatus,
    WebhookTemplateStatus,
    first_phone_number_id,
    parse_webhook,
    verify_signature,
    verify_subscription,
)

__version__ = "0.12.0"

__all__ = [
    # Configuración y transporte
    "GraphConfig",
    "DEFAULT_CONFIG",
    "DEFAULT_API_VERSION",
    "RetryPolicy",
    "DEFAULT_RETRY_POLICY",
    "NO_RETRY_POLICY",
    "Transport",
    # Credenciales
    "WaCredentials",
    "CredentialResolver",
    "StaticCredentialResolver",
    # Medios
    "StorageBackend",
    "StoredMedia",
    "upload_media",
    "upload_resumable",
    "get_media_metadata",
    "delete_media",
    # Clientes
    "MessagesClient",
    "TemplatesClient",
    "NumbersClient",
    "WabaClient",
    "BlockedUsersClient",
    "OAuthClient",
    "builders",
    # Plantillas: creación y envío
    "components",
    "buttons",
    "parameters",
    "build_definition",
    "TemplateCategory",
    "TemplateStatus",
    "ParameterFormat",
    "HeaderFormat",
    "ButtonType",
    "OtpType",
    "FlowAction",
    "FlowIcon",
    "FlowMode",
    # Destinatario
    "digits_only",
    "is_user_id",
    "normalize_recipient",
    "recipient_block",
    # Resultados
    "SendResult",
    "BatchSendResult",
    "TemplateInfo",
    "PhoneNumberInfo",
    "WabaInfo",
    "SubscribedApp",
    "BusinessToken",
    "BlockResult",
    "BusinessProfile",
    "QualityRating",
    "CodeMethod",
    "BusinessVertical",
    # Webhook
    "verify_signature",
    "verify_subscription",
    "parse_webhook",
    "first_phone_number_id",
    "InboundContactCard",
    "WebhookDiscarded",
    "WebhookEvents",
    "WebhookInboundMessage",
    "WebhookStatus",
    "WebhookTemplateStatus",
    # Errores
    "WaCloudError",
    "WaTransportError",
    "WaInvalidRequest",
    "WaRateLimited",
    "WaServerError",
    "MetaError",
    "error_from_response",
    "RetryRule",
    "rule_for_code",
]
