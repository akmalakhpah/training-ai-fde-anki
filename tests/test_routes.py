"""Endpoint tests. This suite ships green.

It exercises the request path against the seeded sample data. It deliberately does
*not* assert the corrected behaviour of the two planted bugs — fixing those (and
adding the tests that pin the fixes) is the Week 1 exercise.
"""

from __future__ import annotations


def test_create_and_get_deck(client):
    created = client.post("/decks", json={"name": "French Basics"})
    assert created.status_code == 200
    deck = created.json()
    assert deck["name"] == "French Basics"

    fetched = client.get(f"/decks/{deck['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["cards"] == []


def test_list_decks(client):
    res = client.get("/decks")
    assert res.status_code == 200
    names = [d["name"] for d in res.json()]
    assert "AI Glossary" in names
    assert "Empty Deck (new)" in names


def test_get_seeded_deck_has_cards(client):
    res = client.get("/decks/1")
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "AI Glossary"
    assert len(body["cards"]) == 6


def test_get_missing_deck_returns_404(client):
    assert client.get("/decks/999").status_code == 404


def test_add_card(client):
    res = client.post("/decks/1/cards", json={"front": "uno", "back": "one"})
    assert res.status_code == 200
    card = res.json()
    assert card["front"] == "uno"
    assert card["deck_id"] == 1


def test_review_advances_schedule(client):
    deck = client.post("/decks", json={"name": "Numbers"}).json()
    card = client.post(
        f"/decks/{deck['id']}/cards", json={"front": "dos", "back": "two"}
    ).json()

    res = client.post(f"/cards/{card['id']}/review", json={"rating": "good"})
    assert res.status_code == 200
    updated = res.json()
    # A "good" review on a brand-new card (interval 0) bumps the interval to 1 day.
    assert updated["interval_days"] == 1


def test_due_returns_a_list(client):
    res = client.get("/decks/1/due")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_stats_on_reviewed_deck(client):
    res = client.get("/decks/1/stats")
    assert res.status_code == 200
    body = res.json()
    assert body["total_cards"] == 6
    assert body["reviews_done"] == 5
    # 3 of 5 seeded reviews were correct (good/easy).
    assert body["retention"] == 0.6


def test_generate_without_key_returns_503(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = client.post("/decks/1/generate", json={"topic": "colors", "count": 3})
    assert res.status_code == 503
    assert res.json()["detail"] == "AI not configured — set ANTHROPIC_API_KEY"
