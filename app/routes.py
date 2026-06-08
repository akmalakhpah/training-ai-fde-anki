"""HTTP endpoints — where requests enter the app.

Each route delegates business logic to services.py and data access to db.py, then
serializes the result through the Pydantic models in models.py.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from . import ai, db, services
from .models import (
    Card,
    CardCreate,
    CardDraft,
    Deck,
    DeckCreate,
    GenerateRequest,
    ReviewCreate,
    Stats,
)

router = APIRouter()


@router.get("/decks", response_model=list[Deck])
def list_decks() -> list[dict]:
    return db.all_decks()


@router.post("/decks", response_model=Deck)
def create_deck(payload: DeckCreate) -> dict:
    return db.insert_deck(payload.name)


@router.get("/decks/{deck_id}", response_model=Deck)
def get_deck(deck_id: int) -> dict:
    deck = db.get_deck(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    deck["cards"] = db.cards_for_deck(deck_id)
    return deck


@router.post("/decks/{deck_id}/cards", response_model=Card)
def add_card(deck_id: int, payload: CardCreate) -> dict:
    if db.get_deck(deck_id) is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return db.insert_card(deck_id, payload.front, payload.back)


@router.get("/decks/{deck_id}/due", response_model=list[Card])
def get_due(deck_id: int) -> list[dict]:
    if db.get_deck(deck_id) is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return services.due_cards(deck_id)


@router.post("/cards/{card_id}/review", response_model=Card)
def review(card_id: int, payload: ReviewCreate) -> dict:
    if db.get_card(card_id) is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return services.review_card(card_id, payload.rating.value)


@router.get("/decks/{deck_id}/stats", response_model=Stats)
def stats(deck_id: int) -> dict:
    if db.get_deck(deck_id) is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return services.deck_stats(deck_id)


@router.post("/decks/{deck_id}/generates", response_model=list[CardDraft])
def generate(deck_id: int, payload: GenerateRequest) -> list[dict]:
    if db.get_deck(deck_id) is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    try:
        drafts = ai.generate_cards(payload.topic, payload.count)
    except ai.AINotConfigured:
        raise HTTPException(
            status_code=503, detail="AI not configured — set ANTHROPIC_API_KEY"
        )
    return [db.insert_card(deck_id, d["front"], d["back"]) for d in drafts]
