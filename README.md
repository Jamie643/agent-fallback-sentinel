# Agent-Fallback-Sentinel
# agent-fallback-sentinel

> Lightweight, production-grade middleware for resilient LLM calls — retries, automated fallback routing, circuit-breaking, and rigid schema validation.

[![CI](https://github.com/Jamie643/agent-fallback-sentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/Jamie643/agent-fallback-sentinel/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/badge/pypi-soon-blue.svg)](#)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## The problem

LLM APIs rate-limit. They return malformed JSON. They go down at 3am.

When that happens mid-agent-workflow, **your entire pipeline dies** — and your users see a 500.

`agent-fallback-sentinel` wraps your LLM calls in a resilience layer that:

- 🔁 **Retries** transient failures with configurable backoff.
- 🛟 **Fails over** to a secondary provider (OpenAI → Anthropic, etc.) automatically.
- 🔌 **Trips a circuit breaker** when all routes are dead, with full error context.
- ✅ **Validates output** against a Pydantic schema — no more `KeyError: 'action'` in prod.
- 📡 **Emits events** so you can plug in your own metrics/tracing.

Zero dependencies beyond `pydantic`.

---

## Install

```bash
pip install agent-fallback-sentinel
```

_(Coming to PyPI. For now: `pip install git+https://github.com/Jamie643/agent-fallback-sentinel.git`)_

---

## Quickstart

```python
from pydantic import BaseModel
from agent_fallback_sentinel import AgentSentinel

class Output(BaseModel):
    status: str
    action: str

sentinel = AgentSentinel(max_retries=2, cooldown=1.0)

result = sentinel.execute_with_fallback(
    primary_fn=call_openai,
    fallback_fn=call_anthropic,
    schema=Output,
)
# -> {"status": "success", "action": "retry_job"}
```

That's it. If `call_openai` rate-limits or returns garbage, `call_anthropic` runs automatically. If both fail, you get a `SentinelCircuitBreaker` with every captured error inside.

---

## Why not just `tenacity`?

`tenacity` is great at retries. It doesn't know about:

- **Multi-provider failover** (a first-class concept here).
- **Schema validation as a failover trigger** — malformed output ≠ retryable; it should fail over immediately.
- **Typed circuit-breaker exceptions** carrying every underlying error for observability.

Think of this as `tenacity` + `pydantic` + failover, purpose-built for LLM calls.

---

## Configuration

| Argument | Default | Description |
|---|---|---|
| `max_retries` | `2` | Retry attempts for the primary provider (excludes the first try). |
| `cooldown` | `1.0` | Seconds between retries on a given provider. |
| `fallback_max_retries` | `1` | Retry attempts for the fallback provider. |
| `sleep_fn` | `time.sleep` | Injectable for testing — pass `lambda _: None` to run instantly. |
| `on_event` | `None` | `Callable[[str, dict], None]` for observability hooks. |

### Events emitted via `on_event`

| Event | When |
|---|---|
| `attempt` | Before each attempt on a provider. |
| `failover` | When primary is exhausted and we switch to fallback. |
| `success` | After a provider returns a schema-valid result. |
| `trip` | When the circuit breaker opens. |

---

## Behavior contract

1. Primary is retried up to `max_retries + 1` times.
2. **Validation errors skip retries** — malformed output won't self-heal. Failover is immediate.
3. Fallback is retried up to `fallback_max_retries + 1` times.
4. If everything fails, `SentinelCircuitBreaker.errors` contains every captured exception, in order.

---

## Real-world example

See [`examples/openai_anthropic_failover.py`](examples/openai_anthropic_failover.py) for a complete OpenAI → Anthropic failover with schema validation.

---

## Development

```bash
git clone https://github.com/Jamie643/agent-fallback-sentinel.git
cd agent-fallback-sentinel
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pytest
```

---

## Roadmap

- [ ] Async support (`aexecute_with_fallback`)
- [ ] Pluggable backoff strategies (exponential, jittered)
- [ ] Native LangChain / LlamaIndex adapters
- [ ] Prometheus metrics exporter

---

## License

MIT — see [LICENSE](LICENSE).
