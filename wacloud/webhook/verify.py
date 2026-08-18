"""Verificación del webhook de Meta: alta de la suscripción y firma de cada POST.

Son dos mecanismos distintos y ambos son obligatorios:

1. **Alta** (``GET``): al guardar o editar la Callback URL, Meta llama con
   ``hub.mode``, ``hub.verify_token`` y ``hub.challenge``. Hay que devolver el challenge
   en texto plano si el token coincide.
2. **Firma** (``POST``): cada notificación llega firmada con HMAC-SHA256 del cuerpo
   usando el ``app_secret``, en el header ``X-Hub-Signature-256``.

La librería no sabe de dónde salen el ``verify_token`` ni el ``app_secret``: los resuelve
el host. Aquí solo se valida.
"""

from __future__ import annotations

import hashlib
import hmac

_PREFIX = "sha256="


def verify_subscription(
    *,
    expected_token: str,
    mode: str | None,
    token: str | None,
    challenge: str | None,
) -> str | None:
    """Valida el alta del webhook y devuelve el challenge a responder.

    Devuelve el ``challenge`` tal cual si la verificación es correcta, o ``None`` si no
    lo es (el host responde entonces 403). El challenge se trata como **cadena opaca**:
    no se convierte a entero ni se reformatea, porque Meta espera exactamente el mismo
    valor de vuelta, en texto plano y sin comillas.

    La comparación del token es en tiempo constante: es un secreto compartido.
    """
    if mode != "subscribe":
        return None
    if not expected_token or not token or not challenge:
        return None
    if not hmac.compare_digest(expected_token, token):
        return None
    return challenge


def compute_signature(app_secret: str, raw_body: bytes) -> str:
    """Valor esperado del header ``X-Hub-Signature-256`` (``sha256=<hex>``)."""
    digest = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"{_PREFIX}{digest}"


def verify_signature(
    *, app_secret: str, raw_body: bytes, signature_header: str | None
) -> bool:
    """``True`` si la firma corresponde al HMAC del cuerpo con ``app_secret``.

    ``raw_body`` debe ser el **cuerpo crudo en bytes**, tal como llegó. Reserializar un
    JSON ya parseado cambia el orden de claves, los espacios y el escapado de unicode,
    y el HMAC deja de cuadrar. En FastAPI: ``await request.body()``, nunca
    ``json.dumps(await request.json())``.

    Nunca lanza: devuelve ``False`` ante cualquier dato ausente o mal formado, para que
    el host pueda responder 403 sin envolver esto en un try.
    """
    if not app_secret or not raw_body or not signature_header:
        return False
    header = signature_header.strip()
    if not header.startswith(_PREFIX):
        return False
    expected = compute_signature(app_secret, raw_body)
    return hmac.compare_digest(expected, header)
