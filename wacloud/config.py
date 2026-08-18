"""Configuración de conexión a la Graph API. Sin secretos y sin política de reintentos.

Los tokens se resuelven por número vía ``CredentialResolver``; los reintentos viven en
``wacloud.retry.RetryPolicy``. Aquí solo queda el "a dónde" y "cuánto espero por la red".
"""

from __future__ import annotations

from dataclasses import dataclass

#: Versión de la Graph API que usa la librería por defecto.
#:
#: Importante: cuando una versión expira, Meta **no devuelve error**; redirige la
#: llamada en silencio a la última versión funcional y el comportamiento cambia sin
#: aviso. Por eso se fija explícitamente y se revisa en cada release de Meta.
#: v19.0 expiró el 21-05-2026 y v20.0 expira el 24-09-2026.
DEFAULT_API_VERSION = "v25.0"


@dataclass(frozen=True)
class GraphConfig:
    """A dónde apunta la librería y cuánto espera por la red."""

    base_url: str = "https://graph.facebook.com"
    api_version: str = DEFAULT_API_VERSION

    connect_timeout: float = 10.0
    read_timeout: float = 30.0

    def graph_url(self, path: str) -> str:
        """URL completa para un path versionado, p. ej. ``/{pnid}/messages``."""
        base = self.base_url.strip().rstrip("/")
        version = self.api_version.strip().strip("/")
        clean_path = path if path.startswith("/") else f"/{path}"
        return f"{base}/{version}{clean_path}"


DEFAULT_CONFIG = GraphConfig()
