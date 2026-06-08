"""SQLite connection and query helpers — the data boundary.

Every request that touches data flows through here. The database file location is
read from the ANKI_DB_PATH environment variable (default: ``anki.db`` in the repo
root), which lets the test suite point at a throwaway database.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "data" / "schema.sql"


def db_path() -> str:
    """Path to the SQLite file. Overridable via ANKI_DB_PATH (used by tests)."""
    return os.environ.get("ANKI_DB_PATH", str(ROOT / "anki.db"))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the tables if they don't exist by running data/schema.sql."""
    schema = SCHEMA_PATH.read_text()
    with connect() as conn:
        conn.executescript(schema)


# --- decks -----------------------------------------------------------------


def insert_deck(name: str) -> dict:
    with connect() as conn:
        cur = conn.execute("INSERT INTO decks (name) VALUES (?)", (name,))
        deck_id = cur.lastrowid
    return get_deck(deck_id)


def get_deck(deck_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
    return dict(row) if row else None


# --- cards -----------------------------------------------------------------


def insert_card(deck_id: int, front: str, back: str) -> dict:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO cards (deck_id, front, back) VALUES (?, ?, ?)",
            (deck_id, front, back),
        )
        card_id = cur.lastrowid
    return get_card(card_id)


def get_card(card_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    return dict(row) if row else None


def cards_for_deck(deck_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM cards WHERE deck_id = ? ORDER BY id", (deck_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def update_card_schedule(
    card_id: int, ease: float, interval_days: int, next_due: str
) -> dict:
    with connect() as conn:
        conn.execute(
            "UPDATE cards SET ease = ?, interval_days = ?, next_due = ? WHERE id = ?",
            (ease, interval_days, next_due, card_id),
        )
    return get_card(card_id)


# --- reviews ---------------------------------------------------------------


def insert_review(card_id: int, rating: str, correct: int) -> dict:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO reviews (card_id, rating, correct) VALUES (?, ?, ?)",
            (card_id, rating, correct),
        )
        review_id = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM reviews WHERE id = ?", (review_id,)
        ).fetchone()
    return dict(row)


def reviews_for_deck(deck_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT reviews.* FROM reviews
            JOIN cards ON cards.id = reviews.card_id
            WHERE cards.deck_id = ?
            ORDER BY reviews.id
            """,
            (deck_id,),
        ).fetchall()
    return [dict(r) for r in rows]
