"""Configuración no sensible de la Graph API (sin tokens ni secretos)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphConfig:
    """Parámetros de conexión a la Graph API de Meta.

    No contiene credenciales: el token y el app_secret se resuelven por número a
    través del ``CredentialResolver``. Esto mantiene la config compartible y libre
    de secretos.
    """

    base_url: str = "https://graph.facebook.com"
    api_version: str = "v19.0"

    # Reintentos del transporte.
    max_retries: int = 3
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 8.0

    # Timeouts (segundos).
    connect_timeout: float = 10.0
    read_timeout: float = 30.0

    def graph_url(self, path: str) -> str:
        """Construye la URL completa para un path versionado, p. ej. ``/{pnid}/messages``."""
        base = self.base_url.strip().rstrip("/")
        version = self.api_version.strip().strip("/")
        clean_path = path if path.startswith("/") else f"/{path}"
        return f"{base}/{version}{clean_path}"


DEFAULT_CONFIG = GraphConfig()
