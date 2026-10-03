"""Custom exception hierarchy for agent-fallback-sentinel."""

from __future__ import annotations


class SentinelError(Exception):
    """Base class for all sentinel errors."""


class SentinelCircuitBreaker(SentinelError):  # noqa: N818
    """
    Raised when every provider route has been exhausted.

    Attributes:
        message: Human-readable summary of the failure.
        errors:  All underlying exceptions captured during the run, in order.
    """

    def __init__(self, message: str, errors: list[Exception] | None = None) -> None:
        super().__init__(message)
        self.errors: list[Exception] = errors or []
