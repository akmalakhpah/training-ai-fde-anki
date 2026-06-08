"""Pydantic request/response models — the serialization boundary."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


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
    topic: str
    count: int


class CardDraft(BaseModel):
    front: str
    back: str
