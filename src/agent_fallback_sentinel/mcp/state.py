"""
Session state for the MCP server.

Holds the current provider configuration and accumulated statistics.
All state is process-scoped — it lives as long as the MCP server runs.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderConfig:
    """One configured provider in the fallback chain."""

    name: str                 # "openai" | "anthropic" | "bedrock" | "ollama"
    model: str                # e.g. "gpt-4o-mini"
    api_key_env: str = ""     # env var name that holds the key
    base_url: str = ""        # for Ollama: "http://localhost:11434"


@dataclass
class CallStats:
    """Accumulated call statistics for the current server session."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    failovers: int = 0
    provider_attempts: dict[str, int] = field(default_factory=dict)
    provider_successes: dict[str, int] = field(default_factory=dict)
    provider_failures: dict[str, int] = field(default_factory=dict)

    def record_attempt(self, provider: str) -> None:
        self.provider_attempts[provider] = self.provider_attempts.get(provider, 0) + 1

    def record_success(self, provider: str) -> None:
        self.provider_successes[provider] = self.provider_successes.get(provider, 0) + 1
        self.successful_calls += 1

    def record_failure(self, provider: str) -> None:
        self.provider_failures[provider] = self.provider_failures.get(provider, 0) + 1
        self.failed_calls += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "failovers": self.failovers,
            "provider_attempts": dict(self.provider_attempts),
            "provider_successes": dict(self.provider_successes),
            "provider_failures": dict(self.provider_failures),
        }


class SessionState:
    """
    Thread-safe, process-scoped state for the MCP server.

    One instance is created at module import and shared by all tools.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._providers: list[ProviderConfig] = []
        self._stats = CallStats()

    # ------------------------------------------------------------------ #
    # Provider configuration
    # ------------------------------------------------------------------ #

    def set_providers(self, providers: list[ProviderConfig]) -> None:
        with self._lock:
            self._providers = list(providers)

    def get_providers(self) -> list[ProviderConfig]:
        with self._lock:
            return list(self._providers)

    def clear_providers(self) -> None:
        with self._lock:
            self._providers = []

    # ------------------------------------------------------------------ #
    # Stats
    # ------------------------------------------------------------------ #

    @property
    def stats(self) -> CallStats:
        return self._stats

    def reset_stats(self) -> None:
        with self._lock:
            self._stats = CallStats()


# Process-wide singleton.
SESSION = SessionState()
