"""Política de reintentos, separada del transporte y de la configuración de endpoint.

Se extrae a su propio módulo por dos razones: cambia por motivos distintos que la URL
de la Graph API (SRP), y así el host puede sustituirla sin tocar ``Transport`` (OCP).

Sobre el backoff: Meta **no documenta el header ``Retry-After``** en ninguna página de
la Cloud API. Lo que sí documenta es esperar ``4^X`` segundos (1, 4, 16, 64, 256) y el
campo ``estimated_time_to_regain_access`` dentro de ``X-Business-Use-Case-Usage``. Por
eso el valor por defecto sigue la progresión de Meta y las pistas del servidor se usan
como refuerzo, no como única estrategia.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """Cuántas veces reintentar y cuánto esperar entre intentos.

    ``max_wait_seconds`` marca la frontera entre "espero aquí" y "esto no es mi
    problema": si Meta exige más que eso (p. ej. las 24 h del código ``131049``),
    bloquear la petición no tiene sentido. En ese caso el error se propaga con
    ``retry_after_seconds`` puesto para que el host lo reprograme cuando quiera.
    """

    max_retries: int = 3
    #: Primer intervalo, en segundos. Meta sugiere empezar en 1 s.
    base_seconds: float = 1.0
    #: Factor de crecimiento. Meta recomienda 4 (1, 4, 16, 64…).
    multiplier: float = 4.0
    #: Tope de una espera individual calculada por nosotros.
    max_seconds: float = 32.0
    #: Espera máxima que aceptamos bloquear dentro del proceso.
    max_wait_seconds: float = 60.0
    #: Jitter completo, para no sincronizar reintentos entre workers.
    jitter: bool = True

    def should_retry(self, attempt: int, *, required_wait: float | None = None) -> bool:
        """Si queda margen para un intento más.

        ``attempt`` es 0 para el primer intento. Una espera exigida que supere
        ``max_wait_seconds`` corta el reintento aunque queden intentos disponibles.
        """
        if attempt >= self.max_retries:
            return False
        return not (required_wait is not None and required_wait > self.max_wait_seconds)

    def delay_for(self, attempt: int, *, server_hint: float | None = None) -> float:
        """Segundos a esperar antes del intento ``attempt + 1``.

        Una pista del servidor (``Retry-After``, o el suelo que impone el código de
        error) actúa como **mínimo**, no como sustituto: si el backoff exponencial ya
        pide más, se respeta el mayor de los dos.
        """
        exponential = self.base_seconds * (self.multiplier**attempt)
        capped = min(exponential, self.max_seconds)
        delay = random.uniform(0.0, capped) if self.jitter else capped

        if server_hint is not None and server_hint > 0:
            delay = max(delay, server_hint)

        return min(delay, self.max_wait_seconds)


#: Política por defecto, alineada con la recomendación de Meta.
DEFAULT_RETRY_POLICY = RetryPolicy()

#: Política para tests y scripts: falla rápido, sin esperas.
NO_RETRY_POLICY = RetryPolicy(max_retries=0, base_seconds=0.0, jitter=False)
