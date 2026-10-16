"""
Provider adapters for OpenAI, Anthropic, AWS Bedrock, and Ollama.

Each adapter exposes the same interface: ``generate(prompt, model) -> str``.
The MCP tools call these adapters through AgentSentinel, so any of them
can serve as the primary or a fallback.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class ProviderError(Exception):
    """Raised when a provider call fails."""


# --------------------------------------------------------------------------- #
# OpenAI
# --------------------------------------------------------------------------- #

def call_openai(prompt: str, model: str = "gpt-4o-mini", **_: Any) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ProviderError("OPENAI_API_KEY not set")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ProviderError("openai package not installed") from exc

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        if content is None:
            raise ProviderError("OpenAI returned empty content")
        return content
    except Exception as exc:  # noqa: BLE001
        raise ProviderError(f"OpenAI failed: {exc}") from exc


# --------------------------------------------------------------------------- #
# Anthropic
# --------------------------------------------------------------------------- #

def call_anthropic(prompt: str, model: str = "claude-3-5-haiku-latest", **_: Any) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ProviderError("ANTHROPIC_API_KEY not set")
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise ProviderError("anthropic package not installed") from exc

    try:
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        # Concatenate text blocks.
        parts = [block.text for block in response.content if hasattr(block, "text")]
        text = "".join(parts)
        if not text:
            raise ProviderError("Anthropic returned empty content")
        return text
    except Exception as exc:  # noqa: BLE001
        raise ProviderError(f"Anthropic failed: {exc}") from exc


# --------------------------------------------------------------------------- #
# AWS Bedrock (Converse API)
# --------------------------------------------------------------------------- #

def call_bedrock(
    prompt: str,
    model: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
    region: str = "us-east-1",
    **_: Any,
) -> str:
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:
        raise ProviderError("boto3 not installed") from exc

    try:
        client = boto3.client("bedrock-runtime", region_name=region)
        response = client.converse(
            modelId=model,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
        )
        text = response["output"]["message"]["content"][0]["text"]
        return str(text)
    except (ClientError, BotoCoreError) as exc:
        raise ProviderError(f"Bedrock failed: {exc}") from exc
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"Bedrock response shape unexpected: {exc}") from exc


# --------------------------------------------------------------------------- #
# Ollama (local)
# --------------------------------------------------------------------------- #

def call_ollama(
    prompt: str,
    model: str = "llama3.1",
    base_url: str = "http://localhost:11434",
    **_: Any,
) -> str:
    """
    Call a local Ollama instance. Uses the /api/generate endpoint.
    """
    url = f"{base_url.rstrip('/')}/api/generate"
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode())
        text = body.get("response", "")
        if not text:
            raise ProviderError("Ollama returned empty response")
        return str(text)
    except urllib.error.URLError as exc:
        raise ProviderError(f"Ollama unreachable at {base_url}: {exc}") from exc
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ProviderError(f"Ollama response shape unexpected: {exc}") from exc


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

PROVIDERS: dict[str, Any] = {
    "openai": call_openai,
    "anthropic": call_anthropic,
    "bedrock": call_bedrock,
    "ollama": call_ollama,
}


def get_provider(name: str) -> Any:
    if name not in PROVIDERS:
        raise ProviderError(
            f"Unknown provider '{name}'. Valid options: {sorted(PROVIDERS.keys())}"
        )
    return PROVIDERS[name]
