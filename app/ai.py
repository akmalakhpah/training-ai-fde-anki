"""The AI feature: draft flashcards from a topic using Claude.

Uses the official Anthropic Python SDK with *tool use* for structured output — we
define a single tool whose input is a list of {front, back} cards and force the
model to call it, so we read cards straight from the tool input with no brittle
string parsing.

If ANTHROPIC_API_KEY is not set, ``generate_cards`` raises ``AINotConfigured`` and
the route turns that into a clean 503 — the rest of the app runs fine without a key.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Card generation is simple, so Haiku keeps per-call cost near zero for a whole
# cohort. The README notes this can be bumped to Sonnet for richer cards.
MODEL = "claude-haiku-4-5-20251001"

_CARD_TOOL = {
    "name": "save_cards",
    "description": "Save the generated flashcards.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cards": {
                "type": "array",
                "description": "The generated flashcards.",
                "items": {
                    "type": "object",
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
                    "required": ["front", "back"],
                },
            }
        },
        "required": ["cards"],
    },
}


class AINotConfigured(RuntimeError):
    """Raised when no ANTHROPIC_API_KEY is available."""


def generate_cards(topic: str, n: int) -> list[dict]:
    """Draft ``n`` flashcards about ``topic``. Each card is a {front, back} dict."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise AINotConfigured("AI not configured — set ANTHROPIC_API_KEY")

    # Imported lazily so the rest of the app imports cleanly even if the SDK or a
    # key is absent.
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=[_CARD_TOOL],
        tool_choice={"type": "tool", "name": "save_cards"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Create exactly {n} flashcards to study the topic: {topic}. "
                    "Each card has a concise front (a question or term) and a back "
                    "(the answer). Save them with the save_cards tool."
                ),
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use":
            cards = block.input.get("cards", [])
            return [{"front": c["front"], "back": c["back"]} for c in cards]
    return []
