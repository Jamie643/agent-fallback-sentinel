"""Custom exception hierarchy for agent-fallback-sentinel."""

from __future__ import annotations

from typing import List, Optional


class SentinelError(Exception):
    """Base class for all sentinel errors."""


class SentinelCircuitBreaker(SentinelError):
    """
    Raised when every provider route has been exhausted.

    Attributes:
        message: Human-readable summary of the failure.
        errors:  All underlying exceptions captured during the run, in order.
    """

    def __init__(self, message: str, errors: Optional[List[Exception]] = None) -> None:
        super().__init__(message)
        self.errors: List[Exception] = errors or []
