"""Business logic: spaced-repetition scheduling, due checks, and deck stats.

This is where a request's logic lives, between the HTTP layer (routes.py) and the
data layer (db.py).
"""

from __future__ import annotations

from datetime import date, timedelta

from . import db

EASE_FLOOR = 1.3


def schedule_next(rating: str, interval: int, ease: float) -> tuple[int, float]:
    """Return (next_interval_days, next_ease) for a card given a recall rating."""
    if rating == "again":
        return 0, max(EASE_FLOOR, ease - 0.20)
    if rating == "hard":
        return max(1, round(interval * 1.2)), max(EASE_FLOOR, ease - 0.15)
    if rating == "good":
        return max(1, round(interval * ease)), ease
    if rating == "easy":
        return max(1, round(interval * ease * 1.3)), ease + 0.15
    raise ValueError(f"unknown rating: {rating}")


def is_due(card: dict, today: str | None = None) -> bool:
    today = today or date.today().isoformat()
    return card["next_due"] >= today


def review_card(card_id: int, rating: str) -> dict:
    """Record a review and advance the card's schedule."""
    card = db.get_card(card_id)
    correct = 1 if rating in ("good", "easy") else 0
    db.insert_review(card_id, rating, correct)

    interval, ease = schedule_next(rating, card["interval_days"], card["ease"])
    next_due = (date.today() + timedelta(days=interval)).isoformat()
    return db.update_card_schedule(card_id, ease, interval, next_due)


def due_cards(deck_id: int) -> list[dict]:
    cards = db.cards_for_deck(deck_id)
    return [c for c in cards if is_due(c)]


def deck_stats(deck_id: int) -> dict:
    cards = db.cards_for_deck(deck_id)
    reviews = db.reviews_for_deck(deck_id)
    correct = sum(r["correct"] for r in reviews)
    retention = correct / len(reviews)
    due = [c for c in cards if is_due(c)]
    return {
        "total_cards": len(cards),
        "due_count": len(due),
        "reviews_done": len(reviews),
        "retention": round(retention, 2),
    }
