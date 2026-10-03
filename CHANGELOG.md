# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-01-01

### Added
- `AgentSentinel` with primary retries, fallback routing, and circuit-breaking.
- `SentinelCircuitBreaker` exception carrying all captured errors.
- Pydantic v2 schema validation with failover-on-invalid-output.
- `on_event` observability hook for `attempt`, `failover`, `success`, `trip`.
- Injectable `sleep_fn` for instant tests.
- Type hints (`py.typed` shipped).
- Test suite covering happy path, retries, failover, circuit breaker, and config validation.
- GitHub Actions CI (Python 3.9–3.12 + ruff + mypy).
