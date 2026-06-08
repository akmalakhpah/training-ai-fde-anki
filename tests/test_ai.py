"""AI endpoint test with the Claude call mocked.

We monkeypatch ``ai.generate_cards`` so CI needs no API key, makes no network call,
and costs nothing — and as a bonus shows how to mock an external dependency.
"""

from __future__ import annotations

from app import ai


def test_generate_inserts_and_returns_drafted_cards(client, monkeypatch):
    canned = [
        {"front": "rojo", "back": "red"},
        {"front": "azul", "back": "blue"},
    ]

    def fake_generate_cards(topic: str, n: int) -> list[dict]:
        assert topic == "colors"
        assert n == 2
        return canned

    monkeypatch.setattr(ai, "generate_cards", fake_generate_cards)

    res = client.post("/decks/1/generate", json={"topic": "colors", "count": 2})
    assert res.status_code == 200
    drafts = res.json()
    assert [{"front": d["front"], "back": d["back"]} for d in drafts] == canned

    # The drafted cards are persisted to the deck.
    deck = client.get("/decks/1").json()
    fronts = [c["front"] for c in deck["cards"]]
    assert "rojo" in fronts and "azul" in fronts
