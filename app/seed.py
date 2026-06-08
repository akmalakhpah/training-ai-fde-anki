"""Seed sample data on a fresh database.

The seed is designed to make both planted bugs observable out of the box:

* Deck 1, "Spanish Basics", has one card due yesterday and one due tomorrow, so
  ``GET /decks/1/due`` reveals whether the due check points the right direction.
* Deck 2, "Empty Deck (new)", has no cards and no reviews, so
  ``GET /decks/2/stats`` exercises the retention calculation on an empty deck.
"""

from __future__ import annotations

from datetime import date, timedelta

from . import db

SPANISH_CARDS = [
    ("hola", "hello"),
    ("gracias", "thank you"),
    ("por favor", "please"),
    ("adiós", "goodbye"),
    ("buenos días", "good morning"),
]


def _set_next_due(card_id: int, next_due: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE cards SET next_due = ? WHERE id = ?", (next_due, card_id)
        )


def seed_if_empty() -> None:
    """Seed sample decks/cards/reviews only when the database has no decks yet."""
    with db.connect() as conn:
        existing = conn.execute("SELECT COUNT(*) AS n FROM decks").fetchone()["n"]
    if existing:
        return
    seed()


def seed() -> None:
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()

    # Deck 1: Spanish Basics — populated, with a mix of due dates and reviews.
    spanish = db.insert_deck("Spanish Basics")
    cards = [
        db.insert_card(spanish["id"], front, back) for front, back in SPANISH_CARDS
    ]

    # One card overdue (yesterday), one scheduled for the future (tomorrow).
    _set_next_due(cards[0]["id"], yesterday)
    _set_next_due(cards[1]["id"], tomorrow)

    # A handful of reviews, mixing correct and incorrect, so stats are sensible.
    db.insert_review(cards[0]["id"], "good", 1)
    db.insert_review(cards[0]["id"], "easy", 1)
    db.insert_review(cards[1]["id"], "again", 0)
    db.insert_review(cards[2]["id"], "good", 1)
    db.insert_review(cards[3]["id"], "hard", 0)

    # Deck 2: Empty Deck (new) — no cards, no reviews.
    db.insert_deck("Empty Deck (new)")
