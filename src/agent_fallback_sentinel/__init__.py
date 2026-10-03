"""
agent-fallback-sentinel
=======================

Lightweight production middleware for resilient LLM calls:
retries, automated fallback routing, circuit-breaking, and rigid schema validation.
"""

from agent_fallback_sentinel.exceptions import SentinelCircuitBreaker, SentinelError
from agent_fallback_sentinel.sentinel import AgentSentinel

__version__ = "0.1.0"

__all__ = [
    "AgentSentinel",
    "SentinelCircuitBreaker",
    "SentinelError",
    "__version__",
]
