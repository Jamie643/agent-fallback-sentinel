"""Tests for the MCP tools — no real provider calls."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agent_fallback_sentinel.mcp import providers as provider_module
from agent_fallback_sentinel.mcp.state import SESSION
from agent_fallback_sentinel.mcp.tools import _make_dynamic_model


@pytest.fixture(autouse=True)
def _reset_session() -> Any:
    SESSION.clear_providers()
    SESSION.reset_stats()
    yield
    SESSION.clear_providers()
    SESSION.reset_stats()


# --------------------------------------------------------------------------- #
# Dynamic schema builder
# --------------------------------------------------------------------------- #

def test_make_dynamic_model_valid() -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name"],
    }
    model = _make_dynamic_model(schema)
    instance = model.model_validate({"name": "Ada", "age": 36})
    assert instance.model_dump() == {"name": "Ada", "age": 36}


def test_make_dynamic_model_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="only 'object'"):
        _make_dynamic_model({"type": "array"})


def test_make_dynamic_model_rejects_bad_property() -> None:
    with pytest.raises(ValueError, match="unsupported type"):
        _make_dynamic_model(
            {"type": "object", "properties": {"x": {"type": "nonsense"}}}
        )


# --------------------------------------------------------------------------- #
# Provider registry
# --------------------------------------------------------------------------- #

def test_get_provider_unknown_raises() -> None:
    with pytest.raises(provider_module.ProviderError):
        provider_module.get_provider("nonsense")


def test_get_provider_known() -> None:
    assert provider_module.get_provider("openai") is provider_module.call_openai
    assert provider_module.get_provider("ollama") is provider_module.call_ollama


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #

def test_session_set_and_get_providers() -> None:
    from agent_fallback_sentinel.mcp.state import ProviderConfig

    configs = [ProviderConfig(name="openai", model="gpt-4o-mini")]
    SESSION.set_providers(configs)
    assert SESSION.get_providers() == configs


def test_session_stats_recording() -> None:
    SESSION.stats.record_attempt("openai")
    SESSION.stats.record_success("openai")
    SESSION.stats.record_attempt("anthropic")
    SESSION.stats.record_failure("anthropic")

    d = SESSION.stats.to_dict()
    assert d["provider_attempts"] == {"openai": 1, "anthropic": 1}
    assert d["provider_successes"] == {"openai": 1}
    assert d["provider_failures"] == {"anthropic": 1}
