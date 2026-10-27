"""Pydantic request/response models — the serialization boundary."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Rating(str, Enum):
    again = "again"
    hard = "hard"
    good = "good"
    easy = "easy"


class DeckCreate(BaseModel):
    name: str


class CardCreate(BaseModel):
    front: str
    back: str


class Card(BaseModel):
    id: int
    deck_id: int
    front: str
    back: str
    ease: float
    interval_days: int
    next_due: str
    created_at: str


class Deck(BaseModel):
    id: int
    name: str
    created_at: str
    cards: list[Card] | None = None


class ReviewCreate(BaseModel):
    rating: Rating


class Stats(BaseModel):
    total_cards: int
    due_count: int
    reviews_done: int
    retention: float


class GenerateRequest(BaseModel):
    # Validation happens here, before any API call — bad input never reaches
    # Claude. ``count`` is bounded (a cost/runaway guardrail too) and ``topic``
    # is capped and required so we never prompt on empty or token-blowing input.
    topic: str = Field(min_length=1, max_length=200)
    count: int = Field(ge=1, le=20)

    @field_validator("topic")
    @classmethod
    def topic_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("topic must not be empty or whitespace")
        return stripped


class CardDraft(BaseModel):
    front: str
    back: str


class CostInfo(BaseModel):
    """Self-reported cost of a generate call, priced from response.usage."""

    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float  # rounded to 6 dp


class GenerateResponse(BaseModel):
    cards: list[Card]  # the inserted cards (with ids/scheduling)
    usage: CostInfo
