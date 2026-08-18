"""Verificación de la firma del webhook de Meta (``X-Hub-Signature-256``).

Meta firma el **body crudo** del POST con HMAC-SHA256 usando el ``app_secret`` de
la app. El header llega como ``sha256=<hexdigest>``. La comparación es en tiempo
constante para evitar timing attacks.

La librería no sabe de dónde sale el ``app_secret`` (lo resuelve el host por
app/número); aquí solo se valida.
"""
from __future__ import annotations

import hashlib
import hmac

_PREFIX = "sha256="


def compute_signature(app_secret: str, raw_body: bytes) -> str:
    """Devuelve el valor esperado del header (``sha256=<hex>``)."""
    digest = hmac.new(
        app_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return f"{_PREFIX}{digest}"


def verify_signature(
    *, app_secret: str, raw_body: bytes, signature_header: str | None
) -> bool:
    """True si ``signature_header`` corresponde al HMAC del body con ``app_secret``.

    Devuelve False ante cualquier dato faltante o formato inválido (nunca lanza),
    para que el host pueda responder 401/403 sin manejar excepciones.
    """
    if not app_secret or not raw_body or not signature_header:
        return False
    header = signature_header.strip()
    if not header.startswith(_PREFIX):
        return False
    expected = compute_signature(app_secret, raw_body)
    return hmac.compare_digest(expected, header)
