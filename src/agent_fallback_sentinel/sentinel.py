"""
Core AgentSentinel implementation.

Executes a primary provider callable, retries transient failures,
fails over to a secondary callable, and enforces a Pydantic schema on
whichever provider ultimately succeeds.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from .exceptions import SentinelCircuitBreaker

logger = logging.getLogger("agent_sentinel")


class AgentSentinel:
    """
    Resilient wrapper for LLM (or any) provider calls.

    Args:
        max_retries: Retries for the primary provider before failover.
        cooldown: Seconds to sleep between retry attempts on a given provider.
        fallback_max_retries: Retries for the fallback provider.
        sleep_fn: Injectable sleep function (defaults to ``time.sleep``).
                  Override in tests to run instantly.
        on_event: Optional callback invoked with (event_name, payload) for
                  observability. Events: "attempt", "failover", "success", "trip".
    """

    def __init__(
        self,
        max_retries: int = 2,
        cooldown: float = 1.0,
        fallback_max_retries: int = 1,
        sleep_fn: Callable[[float], None] = time.sleep,
        on_event: Callable[[str, dict], None] | None = None,
    ) -> None:
        if max_retries < 0 or fallback_max_retries < 0:
            raise ValueError("retry counts must be >= 0")
        if cooldown < 0:
            raise ValueError("cooldown must be >= 0")

        self.max_retries = max_retries
        self.fallback_max_retries = fallback_max_retries
        self.cooldown = cooldown
        self._sleep = sleep_fn
        self._on_event = on_event

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _emit(self, event: str, payload: dict) -> None:
        if self._on_event is not None:
            try:
                self._on_event(event, payload)
            except Exception:  # noqa: BLE001 - never let telemetry break the call
                logger.exception("on_event callback raised; ignoring")

    def _run_with_retries(
        self,
        fn: Callable[[], Any],
        label: str,
        max_retries: int,
        errors: list[Exception],
    ) -> Any:
        """Attempt a callable up to ``max_retries + 1`` times. Raises on final failure."""
        last_exc: Exception = RuntimeError(f"{label} produced no attempts")

        for attempt in range(1, max_retries + 2):
            self._emit("attempt", {"provider": label, "attempt": attempt})
            try:
                logger.info("%s | attempt %d/%d", label, attempt, max_retries + 1)
                return fn()

            except ValidationError:
                # Malformed output — retrying the same provider won't help.
                raise

            except Exception as exc:  # noqa: BLE001 - deliberate broad catch for failover
                logger.warning("%s | attempt %d failed: %s", label, attempt, exc)
                errors.append(exc)
                last_exc = exc
                if attempt <= max_retries:
                    self._sleep(self.cooldown)

        raise last_exc

    def _validate(self, result: Any, schema: type[BaseModel] | None) -> Any:
        if schema is None:
            return result
        return schema.model_validate(result).model_dump()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def execute_with_fallback(
        self,
        primary_fn: Callable[[], Any],
        fallback_fn: Callable[[], Any],
        schema: type[BaseModel] | None = None,
    ) -> Any:
        """
        Run ``primary_fn`` with retries. On exhaustion (or schema failure),
        run ``fallback_fn`` with retries. If both fail, raise
        :class:`SentinelCircuitBreaker`.
        """
        errors: list[Exception] = []

        # --- Phase 1: primary ---
        try:
            raw = self._run_with_retries(primary_fn, "primary", self.max_retries, errors)
            result = self._validate(raw, schema)
            self._emit("success", {"provider": "primary"})
            return result

        except ValidationError as ve:
            logger.warning("primary | schema validation failed, failing over: %s", ve)
            errors.append(ve)
        except Exception as exc:  # noqa: BLE001
            logger.warning("primary | exhausted retries (%s), failing over", exc)

        # --- Phase 2: fallback ---
        self._emit("failover", {"from": "primary", "to": "fallback"})
        logger.info("switching to fallback provider")

        try:
            raw = self._run_with_retries(
                fallback_fn, "fallback", self.fallback_max_retries, errors
            )
            result = self._validate(raw, schema)
            self._emit("success", {"provider": "fallback"})
            return result

        except Exception as fe:  # noqa: BLE001
            errors.append(fe)
            self._emit("trip", {"errors": len(errors)})
            raise SentinelCircuitBreaker(
                f"All provider routes failed after {len(errors)} attempt(s).",
                errors=errors,
            ) from fe
