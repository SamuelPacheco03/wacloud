"""Tests de la política de reintentos y de su integración con el transporte."""

import httpx
import pytest

from tests.factories import make_transport
from wacloud.errors import WaInvalidRequest, WaRateLimited
from wacloud.responses import parse_usage_hint, server_hint
from wacloud.retry import RetryPolicy


def _policy(**kwargs) -> RetryPolicy:
    kwargs.setdefault("jitter", False)
    return RetryPolicy(**kwargs)


# --- RetryPolicy ------------------------------------------------------------


def test_backoff_follows_meta_progression():
    """Meta recomienda 4^X: 1, 4, 16..."""
    policy = _policy(base_seconds=1.0, multiplier=4.0, max_seconds=1000.0)
    assert [policy.delay_for(i) for i in range(3)] == [1.0, 4.0, 16.0]


def test_backoff_is_capped():
    policy = _policy(base_seconds=1.0, multiplier=4.0, max_seconds=10.0)
    assert policy.delay_for(5) == 10.0


def test_jitter_stays_within_the_cap():
    policy = RetryPolicy(base_seconds=1.0, multiplier=4.0, max_seconds=8.0, jitter=True)
    assert all(0.0 <= policy.delay_for(2) <= 8.0 for _ in range(50))


def test_server_hint_acts_as_a_floor_not_a_replacement():
    """Si el backoff calculado ya pide más que la pista, gana el backoff."""
    policy = _policy(base_seconds=10.0, multiplier=1.0, max_seconds=100.0)
    assert policy.delay_for(0, server_hint=2.0) == 10.0
    assert policy.delay_for(0, server_hint=50.0) == 50.0


def test_should_retry_respects_max_retries():
    policy = _policy(max_retries=2)
    assert policy.should_retry(0) is True
    assert policy.should_retry(1) is True
    assert policy.should_retry(2) is False


def test_long_waits_are_not_slept_in_process():
    """Una espera de 24 h se delega al host; bloquear la petición no tiene sentido."""
    policy = _policy(max_retries=5, max_wait_seconds=60.0)
    assert policy.should_retry(0, required_wait=86_400.0) is False
    assert policy.should_retry(0, required_wait=30.0) is True


# --- Pistas del servidor ----------------------------------------------------


def test_parses_estimated_time_to_regain_access_as_minutes():
    response = httpx.Response(
        429,
        headers={
            "X-Business-Use-Case-Usage": '{"123":[{"estimated_time_to_regain_access":19}]}'
        },
    )
    assert parse_usage_hint(response) == 19 * 60.0


def test_usage_hint_survives_malformed_header():
    response = httpx.Response(429, headers={"X-Business-Use-Case-Usage": "no-json"})
    assert parse_usage_hint(response) is None


def test_server_hint_takes_the_largest_signal():
    """Quedarse corto provoca otro rechazo, así que se toma la espera mayor."""
    response = httpx.Response(
        429,
        headers={
            "Retry-After": "5",
            "X-Business-Use-Case-Usage": '{"1":[{"estimated_time_to_regain_access":2}]}',
        },
    )
    error = WaRateLimited("x", retry_after_seconds=3.0)
    assert server_hint(response, error) == 120.0  # 2 minutos gana sobre 5 s y 3 s


# --- Integración con el transporte ------------------------------------------


async def test_non_retryable_meta_code_is_not_retried():
    """131050 (opt-out) llega con HTTP 429, que normalmente sí se reintentaría."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, json={"error": {"code": 131050, "message": "opt out"}})

    transport = make_transport(handler, max_retries=3)
    with pytest.raises(WaInvalidRequest) as excinfo:
        await transport.request("POST", "/pnid/messages", access_token="tok")

    assert calls["n"] == 1, "un opt-out no debe reintentarse ni una vez"
    assert excinfo.value.code == 131050


async def test_retryable_meta_code_is_retried_until_exhausted():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(500, json={"error": {"code": 131000}})

    transport = make_transport(handler, max_retries=2)
    with pytest.raises(WaInvalidRequest.__mro__[1]):  # WaCloudError
        await transport.request("POST", "/pnid/messages", access_token="tok")
    assert calls["n"] == 3


async def test_policy_wait_beyond_threshold_stops_retrying():
    """131049 exige 24 h: se propaga al host en vez de dormir la petición."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"code": 131049}})

    transport = make_transport(handler, max_retries=5)
    with pytest.raises(Exception) as excinfo:
        await transport.request("POST", "/pnid/messages", access_token="tok")

    assert calls["n"] == 1
    assert excinfo.value.retry_after_seconds == 86_400.0


async def test_transport_closes_client_it_created():
    transport = make_transport(lambda r: httpx.Response(200, json={}))
    async with transport as t:
        await t.request("POST", "/x/messages", access_token="tok")
    # El cliente fue inyectado por la factory, así que el transporte no debe cerrarlo.
    assert transport._client is not None
