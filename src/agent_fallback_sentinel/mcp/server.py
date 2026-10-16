"""
MCP server entry point for agent-fallback-sentinel.

Run directly:
    agent-fallback-sentinel-mcp

Or via MCP clients (Claude Desktop, Cursor, etc.) using the config
in ``mcp.json``.
"""

from __future__ import annotations

import logging
import sys

from agent_fallback_sentinel.mcp.tools import register_tools

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("agent_fallback_sentinel.mcp")


def build_server() -> "object":
    """Construct the MCP server with all tools registered."""
    from mcp.server.fastmcp import FastMCP  # imported lazily — optional dep

    mcp = FastMCP(
        "agent-fallback-sentinel",
        instructions=(
            "Resilient LLM calls with automatic provider failover. "
            "First call `configure_providers` to set your provider chain "
            "(openai, anthropic, bedrock, ollama), then use `resilient_llm_call` "
            "for resilient downstream LLM requests. "
            "Use `get_fallback_stats` to inspect failover activity, and "
            "`validate_schema` to enforce structured output."
        ),
    )
    register_tools(mcp)
    return mcp


def main() -> None:
    """Run the MCP server over stdio."""
    logger.info("Starting agent-fallback-sentinel MCP server")
    server = build_server()
    server.run()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
