"""
The MCP tools exposed by agent-fallback-sentinel.

Four tools:

- ``resilient_llm_call`` — resilient LLM call with automatic failover
- ``configure_providers`` — set the provider chain at runtime
- ``get_fallback_stats`` — session-level stats
- ``validate_schema`` — validate JSON against a schema
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ValidationError, create_model

from agent_fallback_sentinel import AgentSentinel, SentinelCircuitBreaker
from agent_fallback_sentinel.mcp.providers import ProviderError, get_provider
from agent_fallback_sentinel.mcp.state import SESSION, ProviderConfig

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _make_callable(provider_name: str, model: str, prompt: str) -> Any:
    """Build a zero-arg callable for AgentSentinel to invoke."""
    provider_fn = get_provider(provider_name)

    def _call() -> str:
        SESSION.stats.record_attempt(provider_name)
        try:
            result = provider_fn(prompt, model=model)
            SESSION.stats.record_success(provider_name)
            return cast(str, result)
        except ProviderError:
            SESSION.stats.record_failure(provider_name)
            raise

    return _call


# --------------------------------------------------------------------------- #
# Tool registration
# --------------------------------------------------------------------------- #

def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools on the given FastMCP instance."""

    @mcp.tool()  # type: ignore[untyped-decorator]
    def configure_providers(
        providers: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Configure the ordered list of LLM providers to try.

        Each entry must have a `name` (one of: openai, anthropic, bedrock, ollama)
        and a `model`. The chain is tried in order; the first success wins.

        Args:
            providers: Ordered list, e.g.
                [
                  {"name": "openai", "model": "gpt-4o-mini"},
                  {"name": "anthropic", "model": "claude-3-5-haiku-latest"},
                  {"name": "ollama", "model": "llama3.1"}
                ]

        Returns:
            Confirmation with the active provider chain.
        """
        if not providers:
            return {
                "status": "error",
                "message": "providers list is empty",
            }

        configs: list[ProviderConfig] = []
        errors: list[str] = []
        for entry in providers:
            name = entry.get("name", "")
            model = entry.get("model", "")
            if not name or not model:
                errors.append(f"entry missing name or model: {entry}")
                continue
            try:
                get_provider(name)
            except ProviderError as exc:
                errors.append(str(exc))
                continue
            configs.append(ProviderConfig(name=name, model=model))

        if errors:
            return {
                "status": "error",
                "message": "some providers are invalid",
                "errors": errors,
            }

        SESSION.set_providers(configs)
        return {
            "status": "ok",
            "providers": [{"name": c.name, "model": c.model} for c in configs],
        }

    @mcp.tool()  # type: ignore[untyped-decorator]
    def resilient_llm_call(
        prompt: str,
        schema_json: str = "",
        max_retries: int = 2,
        cooldown: float = 1.0,
    ) -> dict[str, Any]:
        """
        Make an LLM call with automatic retries and provider failover.

        Tries each configured provider in order. If one fails, moves to the
        next. If `schema_json` is provided, the final response must be valid
        JSON matching that Pydantic-style schema.

        Args:
            prompt: The user-facing prompt to send to the LLM.
            schema_json: Optional JSON-encoded schema. Example:
                '{"type": "object", "properties": {"answer": {"type": "string"}}}'
            max_retries: Retries per provider before failing over (default 2).
            cooldown: Seconds between retries (default 1.0).

        Returns:
            Dict with `status`, `text`, `provider`, `attempts`, and `stats`.
        """
        providers = SESSION.get_providers()
        if not providers:
            return {
                "status": "error",
                "message": "No providers configured. Call configure_providers first.",
            }

        SESSION.stats.total_calls += 1

        schema_model: type[BaseModel] | None = None
        if schema_json:
            try:
                schema_dict = json.loads(schema_json)
                schema_model = _make_dynamic_model(schema_dict)
            except (json.JSONDecodeError, ValueError) as exc:
                return {
                    "status": "error",
                    "message": f"invalid schema_json: {exc}",
                }

        primary = providers[0]
        fallbacks = providers[1:]

        sentinel = AgentSentinel(
            max_retries=max_retries,
            cooldown=cooldown,
            fallback_max_retries=max_retries,
        )

        primary_call = _make_callable(primary.name, primary.model, prompt)
        fallback_call = _make_fallback_chain(fallbacks, prompt)

        try:
            if schema_model is not None:
                result = sentinel.execute_with_fallback(
                    primary_call, fallback_call, schema=schema_model
                )
                return {
                    "status": "ok",
                    "structured": result,
                    "stats": SESSION.stats.to_dict(),
                }

            text = sentinel.execute_with_fallback(primary_call, fallback_call)
            return {
                "status": "ok",
                "text": text,
                "stats": SESSION.stats.to_dict(),
            }
        except SentinelCircuitBreaker as exc:
            return {
                "status": "error",
                "message": f"All providers failed: {exc}",
                "captured_errors": [str(e) for e in exc.errors],
                "stats": SESSION.stats.to_dict(),
            }

    @mcp.tool()  # type: ignore[untyped-decorator]
    def get_fallback_stats() -> dict[str, Any]:
        """
        Return accumulated statistics for the current MCP server session.

        Includes total calls, successes, failures, failover count, and
        per-provider attempt/success/failure breakdowns.
        """
        return SESSION.stats.to_dict()

    @mcp.tool()  # type: ignore[untyped-decorator]
    def validate_schema(
        payload_json: str,
        schema_json: str,
    ) -> dict[str, Any]:
        """
        Validate a JSON payload against a JSON-encoded schema.

        Args:
            payload_json: The data as a JSON string.
            schema_json: The schema as a JSON string.

        Returns:
            Dict with `valid` boolean and either `data` or `errors`.
        """
        try:
            payload = json.loads(payload_json)
            schema_dict = json.loads(schema_json)
        except json.JSONDecodeError as exc:
            return {"valid": False, "errors": [f"invalid JSON: {exc}"]}

        try:
            model = _make_dynamic_model(schema_dict)
            validated = model.model_validate(payload)
            return {"valid": True, "data": validated.model_dump()}
        except ValidationError as exc:
            return {
                "valid": False,
                "errors": [str(e) for e in exc.errors()],
            }
        except ValueError as exc:
            return {"valid": False, "errors": [str(exc)]}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_fallback_chain(fallbacks: list[ProviderConfig], prompt: str) -> Any:
    """
    Build a single callable that tries fallbacks in order.

    AgentSentinel expects a single fallback callable, so we bake the
    chain into one closure.
    """
    def _chain() -> str:
        last_error: Exception | None = None
        for cfg in fallbacks:
            call = _make_callable(cfg.name, cfg.model, prompt)
            try:
                return cast(str, call())
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        raise last_error or RuntimeError("fallback chain empty")

    return _chain


def _make_dynamic_model(schema_dict: dict[str, Any]) -> type[BaseModel]:
    """
    Build a Pydantic model from a JSON-schema-like dict using create_model.

    Supports `type: object` with `properties` mapping field names to
    `{type: string|integer|number|boolean}`.
    """
    if schema_dict.get("type") != "object":
        raise ValueError("only 'object' schemas are supported")

    properties = schema_dict.get("properties")
    if not isinstance(properties, dict) or not properties:
        raise ValueError("schema must have a non-empty 'properties' object")

    required = set(schema_dict.get("required", []))

    type_map: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }

    fields: dict[str, Any] = {}
    for field_name, spec in properties.items():
        if not isinstance(spec, dict):
            raise ValueError(f"property '{field_name}' must be an object")
        type_name = spec.get("type")
        if type_name not in type_map:
            raise ValueError(
                f"property '{field_name}' has unsupported type '{type_name}'"
            )
        if field_name in required:
            fields[field_name] = (type_map[type_name], ...)
        else:
            fields[field_name] = (type_map[type_name] | None, None)

    return cast(type[BaseModel], create_model("DynamicModel", **fields))
