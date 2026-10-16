"""
agent-fallback-sentinel
=======================

Lightweight production middleware for resilient LLM calls:
retries, automated fallback routing, circuit-breaking, and rigid schema validation.

Also ships an MCP server so AI agents can make resilient LLM calls directly.
"""

from agent_fallback_sentinel.exceptions import SentinelCircuitBreaker, SentinelError
from agent_fallback_sentinel.sentinel import AgentSentinel

__version__ = "0.2.0"

__all__ = [
    "AgentSentinel",
    "SentinelCircuitBreaker",
    "SentinelError",
    "__version__",
]
