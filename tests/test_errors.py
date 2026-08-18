"""Tests de la clasificación de errores de Meta.

Lo que se comprueba aquí es la decisión clave del transporte: qué se reintenta, qué no,
y cuánto hay que esperar. Un fallo en esta tabla se traduce en penalizaciones reales de
Meta sobre el número, así que los casos límite van explícitos.
"""

import pytest

from wacloud.error_codes import rule_for_code, rule_for_status
from wacloud.errors import (
    MetaError,
    WaInvalidRequest,
    WaRateLimited,
    WaServerError,
    error_from_response,
)


def _body(code=None, *, message="algo falló", details=None, fbtrace_id=None):
    error = {"message": message}
    if code is not None:
        error["code"] = code
    if details is not None:
        error["error_data"] = {"details": details}
    if fbtrace_id is not None:
        error["fbtrace_id"] = fbtrace_id
    return {"error": error}


# --- MetaError --------------------------------------------------------------


def test_meta_error_extracts_all_fields():
    meta = MetaError.from_body(_body(131049, details="detalle real", fbtrace_id="Az8or2"))
    assert meta.code == 131049
    assert meta.details == "detalle real"
    assert meta.fbtrace_id == "Az8or2"


def test_meta_error_survives_non_dict_body():
    """Un 502 de un proxy llega como HTML, no como JSON de Meta."""
    meta = MetaError.from_body("<html>Bad Gateway</html>")
    assert meta.code is None and meta.message is None


def test_meta_error_parses_code_sent_as_string():
    assert MetaError.from_body({"error": {"code": "131056"}}).code == 131056


def test_meta_error_ignores_bool_as_code():
    """``True`` es un int en Python; no debe colarse como código de error."""
    assert MetaError.from_body({"error": {"code": True}}).code is None


# --- Clasificación de reintentos --------------------------------------------


def test_opt_out_is_never_retryable():
    """131050: el usuario rechazó marketing. Reintentar no cambia nada."""
    error = error_from_response(400, _body(131050))
    assert error.retryable is False
    assert error.code == 131050


def test_blocked_by_business_is_never_retryable():
    assert error_from_response(400, _body(130403)).retryable is False


def test_marketing_limit_demands_a_24h_wait():
    """131049: reintentar antes de 24 h añade otras 24 h de penalización."""
    error = error_from_response(400, _body(131049))
    assert error.retryable is True
    assert error.retry_after_seconds == 86_400.0


def test_pair_rate_limit_is_rate_limited_despite_non_429_status():
    """131056 no llega como HTTP 429: clasificar solo por status lo perdería."""
    error = error_from_response(400, _body(131056))
    assert isinstance(error, WaRateLimited)
    assert error.retry_after_seconds == 6.0


def test_throughput_limit_is_rate_limited():
    assert isinstance(error_from_response(400, _body(130429)), WaRateLimited)


def test_unknown_code_falls_back_to_status_heuristic():
    """Un código sin catalogar no debe asumirse reintentable ni permanente."""
    assert rule_for_code(999_999) is None
    assert error_from_response(503, _body(999_999)).retryable is True
    assert error_from_response(400, _body(999_999)).retryable is False


def test_server_error_without_code_is_retryable():
    error = error_from_response(500, "unavailable")
    assert isinstance(error, WaServerError)
    assert error.retryable is True


def test_validation_error_without_code_is_not_retryable():
    error = error_from_response(400, "bad request")
    assert isinstance(error, WaInvalidRequest)
    assert error.retryable is False


def test_http_429_without_code_is_rate_limited():
    assert isinstance(error_from_response(429, {}), WaRateLimited)


@pytest.mark.parametrize("code", [2, 4, 80007, 131000, 131016, 131057, 133004])
def test_documented_transient_codes_are_retryable(code):
    assert rule_for_code(code).retryable is True


@pytest.mark.parametrize("code", [131021, 131026, 131047, 132000, 132016, 134100])
def test_documented_permanent_codes_are_not_retryable(code):
    assert rule_for_code(code).retryable is False


def test_message_includes_code_and_details():
    message = str(error_from_response(400, _body(131047, details="ventana cerrada")))
    assert "131047" in message and "ventana cerrada" in message


def test_status_heuristic_shapes():
    assert rule_for_status(429).retryable is True
    assert rule_for_status(500).retryable is True
    assert rule_for_status(404).retryable is False
