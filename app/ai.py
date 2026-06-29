"""The AI feature: draft flashcards from a topic using Claude.

Uses the official Anthropic Python SDK with *tool use* for structured output — we
define a single tool whose input is a list of {front, back} cards and force the
model to call it, so we read cards straight from the tool input with no brittle
string parsing. The tool is marked ``strict`` so the input is guaranteed to match
the schema (supported on Haiku 4.5).

Hardening (Week 4):
- ``GenerateRequest`` validates input *before* we get here (see models.py).
- We validate every card and drop any missing a non-empty ``front``/``back``.
- One application-level retry: if a response yields no usable cards (no tool
  block, or every card fails validation) we try once more, then raise
  ``AINoUsableCards`` so the route returns a clean 502 — we never insert junk and
  never 500. The SDK's built-in ``max_retries`` handles transient 429/5xx beneath
  this.
- We read ``response.usage`` and price it from a per-model rate table, returning a
  ``CostInfo`` alongside the cards.

If ANTHROPIC_API_KEY is not set, ``generate_cards`` raises ``AINotConfigured`` and
the route turns that into a clean 503 — the rest of the app runs fine without a key.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from .models import CostInfo

load_dotenv()

# Card generation is simple, so Haiku keeps per-call cost near zero for a whole
# cohort. The README notes this can be bumped to Sonnet for richer cards.
MODEL = "claude-haiku-4-5-20251001"

# USD per 1M tokens, (input, output). Keyed by model-id prefix so a dated
# snapshot (e.g. claude-haiku-4-5-20251001) matches its base entry.
RATES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
}

# v2 prompt — see docs/plan.md "Prompt versions". A system prompt frames the role
# and handles ambiguous/empty topics gracefully; the user turn pins the count.
_SYSTEM_PROMPT = (
    "You are a flashcard author. You always produce exactly the requested number "
    "of cards and you always return them via the save_cards tool — never as prose. "
    "Keep each front a single question or term and each back a concise answer. Do "
    "not produce duplicate cards. If the topic is too vague to study, produce the "
    "best general-knowledge cards you can rather than refusing."
)

_CARD_TOOL = {
    "name": "save_cards",
    "description": "Save the generated flashcards.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["cards"],
        "properties": {
            "cards": {
                "type": "array",
                "description": "The generated flashcards.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["front", "back"],
                    "properties": {
                        "front": {
                            "type": "string",
                            "description": "The prompt side of the card (a question or term).",
                        },
                        "back": {
                            "type": "string",
                            "description": "The answer side of the card.",
                        },
                    },
                },
            }
        },
    },
}


class AINotConfigured(RuntimeError):
    """Raised when no ANTHROPIC_API_KEY is available."""


class AINoUsableCards(RuntimeError):
    """Raised when the model returns nothing usable after a retry (→ 502)."""


def _user_prompt(topic: str, n: int) -> str:
    return (
        f"Create exactly {n} flashcards to study the topic: {topic}. Each card has "
        "a concise front (a question or term) and a back (the answer). Save them "
        f"with the save_cards tool. Return exactly {n} cards, no more, no less."
    )


def _rate_for(model: str) -> tuple[float, float]:
    for prefix, rate in RATES.items():
        if model.startswith(prefix):
            return rate
    return RATES["claude-haiku-4-5"]


def _price(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = _rate_for(model)
    cost = input_tokens / 1e6 * in_rate + output_tokens / 1e6 * out_rate
    return round(cost, 6)


def _extract_cards(response) -> list[dict]:
    """Pull validated cards from the tool_use block. Drops any card missing a
    non-empty string front/back; returns [] if there's no tool block at all."""
    for block in response.content:
        if block.type == "tool_use":
            valid: list[dict] = []
            for card in block.input.get("cards", []):
                if not isinstance(card, dict):
                    continue
                front, back = card.get("front"), card.get("back")
                if (
                    isinstance(front, str)
                    and front.strip()
                    and isinstance(back, str)
                    and back.strip()
                ):
                    valid.append({"front": front, "back": back})
            return valid
    return []


def generate_cards(topic: str, n: int) -> tuple[list[dict], CostInfo]:
    """Draft ``n`` flashcards about ``topic``.

    Returns ``(cards, cost)`` where each card is a ``{front, back}`` dict and
    ``cost`` is a ``CostInfo`` read from ``response.usage``. Raises
    ``AINotConfigured`` with no key, or ``AINoUsableCards`` when two attempts
    yield nothing usable.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise AINotConfigured("AI not configured — set ANTHROPIC_API_KEY")

    # Imported lazily so the rest of the app imports cleanly even if the SDK or a
    # key is absent.
    import anthropic

    client = anthropic.Anthropic()

    total_in = total_out = 0
    model_used = MODEL

    # One application-level retry: attempt 0, then attempt 1 on failure.
    for attempt in range(2):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                tools=[_CARD_TOOL],
                tool_choice={"type": "tool", "name": "save_cards"},
                messages=[{"role": "user", "content": _user_prompt(topic, n)}],
            )
        except anthropic.APIError as exc:
            # SDK already retried transient 429/5xx; if it still failed, retry
            # once at the app level, then give up with a clean 502.
            if attempt == 1:
                raise AINoUsableCards("AI request failed") from exc
            continue

        total_in += response.usage.input_tokens
        total_out += response.usage.output_tokens
        model_used = response.model

        cards = _extract_cards(response)
        if cards:
            cost = CostInfo(
                model=model_used,
                input_tokens=total_in,
                output_tokens=total_out,
                cost_usd=_price(model_used, total_in, total_out),
            )
            return cards, cost
        # No usable cards — loop retries once with the same (v2) prompt.

    raise AINoUsableCards("AI returned no usable cards")
