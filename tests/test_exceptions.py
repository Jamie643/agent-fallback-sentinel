"""Tests for the exception hierarchy."""

from agent_fallback_sentinel import SentinelCircuitBreaker, SentinelError


def test_sentinel_circuit_breaker_is_sentinel_error():
    assert issubclass(SentinelCircuitBreaker, SentinelError)


def test_sentinel_circuit_breaker_carries_errors():
    underlying = [RuntimeError("a"), ValueError("b")]
    exc = SentinelCircuitBreaker("all routes failed", errors=underlying)
    assert exc.errors == underlying
    assert "all routes failed" in str(exc)


def test_sentinel_circuit_breaker_default_errors_empty():
    exc = SentinelCircuitBreaker("boom")
    assert exc.errors == []
