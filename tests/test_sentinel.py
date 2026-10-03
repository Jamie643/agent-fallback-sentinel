"""Test suite for AgentSentinel."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from agent_fallback_sentinel import AgentSentinel, SentinelCircuitBreaker


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

class OutputSchema(BaseModel):
    status: str
    action: str


@pytest.fixture
def no_sleep_sentinel():
    """Sentinel with max_retries=2 and no actual sleeping."""
    return AgentSentinel(
        max_retries=2, cooldown=0.0, fallback_max_retries=1, sleep_fn=lambda _: None
    )


def _make_callable(results):
    """Return a callable that returns/raises items from `results` in order."""
    iterator = iter(results)
    calls = {"count": 0}

    def fn():
        calls["count"] += 1
        item = next(iterator)
        if isinstance(item, Exception):
            raise item
        return item

    return fn, calls


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #

def test_primary_succeeds_immediately(no_sleep_sentinel):
    primary, calls = _make_callable([{"status": "ok", "action": "run"}])
    fallback, fb_calls = _make_callable([{"status": "fb", "action": "run"}])

    out = no_sleep_sentinel.execute_with_fallback(primary, fallback, schema=OutputSchema)

    assert out == {"status": "ok", "action": "run"}
    assert calls["count"] == 1
    assert fb_calls["count"] == 0


def test_primary_succeeds_on_retry(no_sleep_sentinel):
    primary, calls = _make_callable([
        RuntimeError("429"),
        {"status": "ok", "action": "run"},
    ])
    fallback, fb_calls = _make_callable([{"status": "fb", "action": "run"}])

    out = no_sleep_sentinel.execute_with_fallback(primary, fallback, schema=OutputSchema)

    assert out["status"] == "ok"
    assert calls["count"] == 2
    assert fb_calls["count"] == 0


# --------------------------------------------------------------------------- #
# Failover
# --------------------------------------------------------------------------- #

def test_fails_over_after_primary_exhausted(no_sleep_sentinel):
    primary, calls = _make_callable([
        RuntimeError("429"),
        RuntimeError("429"),
        RuntimeError("429"),
    ])
    fallback, fb_calls = _make_callable([{"status": "fb", "action": "retry"}])

    out = no_sleep_sentinel.execute_with_fallback(primary, fallback, schema=OutputSchema)

    assert out == {"status": "fb", "action": "retry"}
    assert calls["count"] == 3   # 1 + max_retries (2)
    assert fb_calls["count"] == 1


def test_schema_failure_skips_retries_and_fails_over(no_sleep_sentinel):
    """Malformed output should fail over immediately, not retry the primary."""
    primary, calls = _make_callable([{"wrong": "shape"}])
    fallback, fb_calls = _make_callable([{"status": "fb", "action": "ok"}])

    out = no_sleep_sentinel.execute_with_fallback(primary, fallback, schema=OutputSchema)

    assert out == {"status": "fb", "action": "ok"}
    assert calls["count"] == 1
    assert fb_calls["count"] == 1


# --------------------------------------------------------------------------- #
# Circuit breaker
# --------------------------------------------------------------------------- #

def test_circuit_breaker_trips_when_both_fail(no_sleep_sentinel):
    primary, _ = _make_callable([RuntimeError("down")] * 3)
    fallback, _ = _make_callable([RuntimeError("also down")] * 2)

    with pytest.raises(SentinelCircuitBreaker) as excinfo:
        no_sleep_sentinel.execute_with_fallback(primary, fallback, schema=OutputSchema)

    assert len(excinfo.value.errors) >= 4
    assert any(isinstance(e, RuntimeError) for e in excinfo.value.errors)


# --------------------------------------------------------------------------- #
# No schema
# --------------------------------------------------------------------------- #

def test_no_schema_passthrough(no_sleep_sentinel):
    primary, _ = _make_callable(["raw string result"])
    fallback, _ = _make_callable(["nope"])

    out = no_sleep_sentinel.execute_with_fallback(primary, fallback, schema=None)
    assert out == "raw string result"


# --------------------------------------------------------------------------- #
# Config validation
# --------------------------------------------------------------------------- #

def test_negative_retries_rejected():
    with pytest.raises(ValueError):
        AgentSentinel(max_retries=-1)

    with pytest.raises(ValueError):
        AgentSentinel(fallback_max_retries=-1)


def test_negative_cooldown_rejected():
    with pytest.raises(ValueError):
        AgentSentinel(cooldown=-0.1)


# --------------------------------------------------------------------------- #
# Observability
# --------------------------------------------------------------------------- #

def test_on_event_callback_receives_events():
    events = []
    sentinel = AgentSentinel(
        max_retries=1,
        cooldown=0.0,
        sleep_fn=lambda _: None,
        on_event=lambda name, payload: events.append((name, payload)),
    )

    primary, _ = _make_callable([RuntimeError("x"), RuntimeError("y")])
    fallback, _ = _make_callable([{"status": "ok", "action": "z"}])

    sentinel.execute_with_fallback(primary, fallback, schema=OutputSchema)

    names = [e[0] for e in events]
    assert "attempt" in names
    assert "failover" in names
    assert "success" in names


def test_on_event_callback_exceptions_are_swallowed(no_sleep_sentinel):
    """A broken on_event handler must not break the pipeline."""
    def bad_handler(_name, _payload):
        raise RuntimeError("telemetry is broken")

    sentinel = AgentSentinel(
        max_retries=0, cooldown=0.0, sleep_fn=lambda _: None, on_event=bad_handler
    )
    primary, _ = _make_callable([{"status": "ok", "action": "run"}])
    fallback, _ = _make_callable([{"status": "fb", "action": "run"}])

    out = sentinel.execute_with_fallback(primary, fallback, schema=OutputSchema)
    assert out["status"] == "ok"
