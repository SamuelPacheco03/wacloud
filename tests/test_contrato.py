"""La convención de retorno de los clientes, como gate y no solo como párrafo.

El `CLAUDE.md` la explica; esto la comprueba. La distinción importa: la regla llevaba 37
de 40 métodos cumpliéndose sola, y las tres excepciones —`edit`, `delete` y `mark_read`,
que devolvían el ``dict`` crudo de Meta— sobrevivieron a varias versiones sin que nada se
quejara. El coste lo pagó el host: acabó inventándose un nombre distinto por ruta para
decir "salió bien", porque no había nada normalizado que traducir.

Recorre las clases de verdad, así que un método nuevo entra aquí solo.
"""

from __future__ import annotations

import inspect
from typing import Any, get_type_hints

import pytest

from wacloud import (
    BlockedUsersClient,
    MessagesClient,
    NumbersClient,
    OAuthClient,
    TemplatesClient,
    WabaClient,
)

CLIENTS = (
    MessagesClient,
    TemplatesClient,
    NumbersClient,
    BlockedUsersClient,
    WabaClient,
    OAuthClient,
)


def _public_methods() -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    for client in CLIENTS:
        for name, member in vars(client).items():
            if name.startswith("_") or not inspect.isfunction(member):
                continue
            returns = get_type_hints(member).get("return", Any)
            found.append((f"{client.__name__}.{name}", returns))
    return found


def test_there_are_methods_to_check():
    """Si el recorrido deja de encontrar métodos, los tests de abajo pasan vacíos."""
    assert len(_public_methods()) > 30


@pytest.mark.parametrize(("name", "returns"), _public_methods())
def test_no_client_returns_metas_raw_dict(name: str, returns: Any):
    """Un `dict[str, Any]` en la firma es la forma de Meta escapándose al host.

    Es la línea que separa esta librería de un `httpx` con azúcar: si el host tiene que
    leer el esquema de Meta para saber si algo salió bien, no le hemos ahorrado nada. Para
    el detalle que no cabe en la firma está `raw` dentro del modelo.
    """
    assert returns is not Any, f"{name} no declara qué devuelve"
    assert getattr(returns, "__origin__", None) is not dict, (
        f"{name} devuelve el dict crudo de Meta"
    )
