"""
agent-fallback-sentinel
-----------------------
Lightweight production middleware for resilient LLM calls:
retries, automated fallback routing, circuit-breaking, and rigid schema validation.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional, Type

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("agent_sentinel")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class SentinelCircuitBreaker(Exception):
    """Raised when every provider route has been exhausted."""

    def __init__(self, message: str, errors: Optional[list[Exception]] = None):
        super().__init__(message)
        self.errors = errors or []


class AgentSentinel:
    """
    Executes a primary LLM callable, retries transient failures,
    fails over to a secondary callable, and enforces a Pydantic schema
    on whichever provider ultimately succeeds.

    Schema validation failures skip retries on the primary (a malformed
    output will not self-heal) and go straight to fallback.
    """

    def __init__(
        self,
        max_retries: int = 2,
        cooldown: float = 1.0,
        fallback_max_retries: int = 1,
    ):
        if max_retries < 0 or fallback_max_retries < 0:
            raise ValueError("retry counts must be >= 0")
        self.max_retries = max_retries
        self.fallback_max_retries = fallback_max_retries
        self.cooldown = cooldown

    def _run_with_retries(
        self,
        fn: Callable[[], Any],
        label: str,
        max_retries: int,
        errors: list[Exception],
    ) -> Any:
        """Attempt a callable up to max_retries+1 times. Raises on final failure."""
        for attempt in range(1, max_retries + 2):
            try:
                logger.info("%s | attempt %d/%d", label, attempt, max_retries + 1)
                return fn()
            except ValidationError:
                # Malformed output — retrying the same provider is unlikely to help.
                raise
            except Exception as exc:
                logger.warning("%s | attempt %d failed: %s", label, attempt, exc)
                errors.append(exc)
                if attempt <= max_retries:
                    time.sleep(self.cooldown)
        raise errors[-1]

    def _validate(self, result: Any, schema: Optional[Type[BaseModel]]) -> Any:
        if schema is None:
            return result
        validated = schema.model_validate(result)
        return validated.model_dump()

    def execute_with_fallback(
        self,
        primary_fn: Callable[[], Any],
        fallback_fn: Callable[[], Any],
        schema: Optional[Type[BaseModel]] = None,
    ) -> Any:
        errors: list[Exception] = []

        # Phase 1: primary provider (with retries)
        try:
            raw = self._run_with_retries(
                primary_fn, "primary", self.max_retries, errors
            )
            return self._validate(raw, schema)
        except ValidationError as ve:
            logger.warning("primary | schema validation failed, failing over: %s", ve)
            errors.append(ve)
        except Exception:
            logger.warning("primary | exhausted retries, failing over")

        # Phase 2: fallback provider (with retries)
        logger.info("switching to fallback provider")
        try:
            raw = self._run_with_retries(
                fallback_fn, "fallback", self.fallback_max_retries, errors
            )
            return self._validate(raw, schema)
        except Exception as fe:
            errors.append(fe)
            raise SentinelCircuitBreaker(
                f"All provider routes failed after {len(errors)} attempt(s).",
                errors=errors,
            ) from fe


# ---------------------------------------------------------------------------
# Usage example / smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":

    class OutputSchema(BaseModel):
        status: str
        action: str

    sentinel = AgentSentinel(max_retries=1, cooldown=0.2)

    def primary_llm() -> dict:
        raise RuntimeError("429 Rate Limit Exceeded")

    def backup_llm() -> dict:
        return {"status": "success", "action": "retry_job"}

    result = sentinel.execute_with_fallback(
        primary_llm, backup_llm, schema=OutputSchema
    )
    print("Sentinel handled execution cleanly:", result)

    # Demonstrate circuit-breaker when both providers die
    def dead(_msg: str = "500 Internal Server Error") -> dict:
        raise RuntimeError("500 Internal Server Error")

    try:
        sentinel.execute_with_fallback(dead, dead, schema=OutputSchema)
    except SentinelCircuitBreaker as cb:
        print(f"Circuit breaker tripped as expected: {cb} "
              f"(captured {len(cb.errors)} underlying errors)")
