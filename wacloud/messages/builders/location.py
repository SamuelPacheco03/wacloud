"""Mensajes de ubicación."""

from __future__ import annotations

from typing import Any

from wacloud.recipient import recipient_block

__all__ = ["build_location"]

_LATITUDE_RANGE = (-90.0, 90.0)
_LONGITUDE_RANGE = (-180.0, 180.0)


def _coordinate(value: float | str, *, field: str, bounds: tuple[float, float]) -> str:
    """Valida una coordenada y la devuelve como cadena.

    Meta documenta latitud y longitud como *String*, aunque su esquema OpenAPI use
    números y ambos funcionen. Se manda cadena por seguir la documentación.

    Validar el rango detecta el error clásico de intercambiar los dos valores: una
    longitud válida de 120 puesta como latitud es imposible, y sin esta comprobación
    Meta la acepta y sitúa el pin en otro continente.
    """
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}: {value!r} no es una coordenada válida") from exc

    low, high = bounds
    if not low <= number <= high:
        raise ValueError(
            f"{field}: {number} está fuera del rango [{low}, {high}] "
            "(¿latitud y longitud intercambiadas?)"
        )
    return str(value).strip() if isinstance(value, str) else repr(number)


def build_location(
    to: str,
    *,
    latitude: float | str,
    longitude: float | str,
    name: str | None = None,
    address: str | None = None,
) -> dict[str, Any]:
    """Comparte una ubicación en el mapa.

    ``name`` y ``address`` son opcionales, pero Meta solo muestra la dirección si además
    hay nombre: mandar ``address`` a solas no aporta nada, así que se exige el par.
    """
    location: dict[str, Any] = {
        "latitude": _coordinate(latitude, field="latitude", bounds=_LATITUDE_RANGE),
        "longitude": _coordinate(longitude, field="longitude", bounds=_LONGITUDE_RANGE),
    }
    clean_name = str(name or "").strip()
    clean_address = str(address or "").strip()

    if clean_address and not clean_name:
        raise ValueError(
            "'address' necesita 'name': WhatsApp no muestra la dirección sin el nombre"
        )
    if clean_name:
        location["name"] = clean_name
    if clean_address:
        location["address"] = clean_address

    return {**recipient_block(to), "type": "location", "location": location}
