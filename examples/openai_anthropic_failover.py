"""
Real-world example: fail over from OpenAI to Anthropic on rate limits.

Run:
    pip install openai anthropic
    export OPENAI_API_KEY=sk-...
    export ANTHROPIC_API_KEY=sk-ant-...
    python examples/openai_anthropic_failover.py
"""

from __future__ import annotations

import os

from pydantic import BaseModel

from agent_fallback_sentinel import AgentSentinel, SentinelCircuitBreaker


class TicketTriage(BaseModel):
    category: str
    urgency: str
    suggested_action: str


PROMPT = (
    "Classify this support ticket and respond as JSON with keys "
    "'category', 'urgency', 'suggested_action'. "
    "Ticket: 'My dashboard has been loading forever since yesterday.'"
)


def call_openai() -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": PROMPT}],
        response_format={"type": "json_object"},
    )
    import json

    return json.loads(resp.choices[0].message.content or "{}")


def call_anthropic() -> dict:
    import json

    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-3-5-haiku-latest",
        max_tokens=256,
        messages=[{"role": "user", "content": PROMPT}],
    )
    return json.loads(resp.content[0].text)


def main() -> None:
    sentinel = AgentSentinel(
        max_retries=2,
        cooldown=1.0,
        fallback_max_retries=1,
        on_event=lambda name, payload: print(f"[sentinel] {name}: {payload}"),
    )

    try:
        result = sentinel.execute_with_fallback(
            primary_fn=call_openai,
            fallback_fn=call_anthropic,
            schema=TicketTriage,
        )
        print("Triage result:", result)
    except SentinelCircuitBreaker as exc:
        print(f"All providers failed ({len(exc.errors)} errors captured).")
        for err in exc.errors:
            print(" -", err)


if __name__ == "__main__":
    main()
