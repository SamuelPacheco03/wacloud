"""Ejecuta todas las comprobaciones de calidad en un solo comando.

    python scripts/check.py            # formato, lint, tipos y tests
    python scripts/check.py --fix      # además arregla formato y lint

Existe como script de Python y no como Makefile porque en Windows no hay ``make``, y la
alternativa era que cada uno recordara cuatro comandos distintos. Es el mismo conjunto
que ejecuta la CI: si esto pasa en local, la CI pasa.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(name: str, command: list[str]) -> bool:
    """Ejecuta un comando y devuelve si terminó bien.

    La salida es ASCII puro a propósito: la consola de Windows usa cp1252 por defecto y
    falla con caracteres de dibujo o emojis.
    """
    print(f"\n=== {name} ===", flush=True)
    # check=False a propósito: aquí interesa recoger todos los fallos y reportarlos
    # juntos al final, no abortar en el primero.
    completed = subprocess.run([sys.executable, "-m", *command], cwd=ROOT, check=False)
    return completed.returncode == 0


def main() -> int:
    fix = "--fix" in sys.argv

    formato = ["ruff", "format", "."] if fix else ["ruff", "format", "--check", "."]
    lint = ["ruff", "check", "--fix", "."] if fix else ["ruff", "check", "."]

    checks: list[tuple[str, list[str]]] = [
        ("Formato", formato),
        ("Lint", lint),
        ("Tipos (mypy strict)", ["mypy", "wacloud/"]),
        ("Tests", ["pytest", "-q", "--cov=wacloud", "--cov-report=term-missing"]),
    ]

    failed = [name for name, command in checks if not run(name, command)]

    print()
    if failed:
        print(f"FALLO: {', '.join(failed)}")
        return 1
    print("Todo correcto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
