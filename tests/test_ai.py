"""Tests for the hardened /generate feature — fully mocked.

No network, no API key required. We fake the Anthropic client by patching
``anthropic.Anthropic`` (the SDK is imported lazily inside ``generate_cards``), so
we can drive well-formed, malformed, and retry scenarios deterministically.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import ai


# --- fakes -----------------------------------------------------------------


def _response(cards, *, input_tokens=250, output_tokens=400, model=ai.MODEL):
    """Build a fake Messages response with a forced save_cards tool_use block.

    Pass ``cards=None`` to simulate a response with *no* tool_use block.
    """
    content = []
    if cards is not None:
        content.append(SimpleNamespace(type="tool_use", input={"cards": cards}))
    return SimpleNamespace(
        content=content,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        model=model,
    )


class _FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def create(self, **kwargs):
        item = self._responses[self.calls]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


class _FakeClient:
    def __init__(self, responses):
        self.messages = _FakeMessages(responses)


def _install(monkeypatch, responses):
    """Point generate_cards at a fake client that returns ``responses`` in order."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import anthropic

    client = _FakeClient(responses)
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: client)
    return client


# --- generate_cards unit tests ---------------------------------------------


def test_well_formed_response_returns_cards_and_cost(monkeypatch):
    cards = [{"front": "rojo", "back": "red"}, {"front": "azul", "back": "blue"}]
    _install(monkeypatch, [_response(cards, input_tokens=250, output_tokens=400)])

    result, cost = ai.generate_cards("colors", 2)

    assert result == cards
    assert cost.model.startswith("claude-haiku-4-5")
    assert cost.input_tokens == 250
    assert cost.output_tokens == 400


def test_cost_math_is_priced_from_usage(monkeypatch):
    _install(
        monkeypatch,
        [_response([{"front": "q", "back": "a"}], input_tokens=1_000_000,
                   output_tokens=1_000_000, model="claude-haiku-4-5-20251001")],
    )

    _, cost = ai.generate_cards("anything", 1)

    # Haiku 4.5: $1.00/1M in + $5.00/1M out → 1M+1M = $6.00.
    assert cost.cost_usd == 6.0


def test_sonnet_cost_uses_sonnet_rates(monkeypatch):
    _install(
        monkeypatch,
        [_response([{"front": "q", "back": "a"}], input_tokens=1_000_000,
                   output_tokens=1_000_000, model="claude-sonnet-4-6")],
    )

    _, cost = ai.generate_cards("anything", 1)

    # Sonnet 4.6: $3.00/1M in + $15.00/1M out → $18.00.
    assert cost.cost_usd == 18.0


def test_invalid_cards_are_dropped(monkeypatch):
    cards = [
        {"front": "good", "back": "card"},
        {"front": "", "back": "empty front"},
        {"front": "no back", "back": "   "},
        {"front": "missing back"},
    ]
    _install(monkeypatch, [_response(cards)])

    result, _ = ai.generate_cards("topic", 4)

    assert result == [{"front": "good", "back": "card"}]


def test_malformed_first_response_then_good_retry(monkeypatch):
    good = [{"front": "uno", "back": "one"}]
    client = _install(
        monkeypatch,
        [_response(None), _response(good)],  # no tool block, then a good one
    )

    result, cost = ai.generate_cards("numbers", 1)

    assert result == good
    assert client.messages.calls == 2
    # Cost accumulates across both attempts.
    assert cost.input_tokens == 500
    assert cost.output_tokens == 800


def test_both_malformed_raises_no_usable_cards(monkeypatch):
    client = _install(monkeypatch, [_response(None), _response([])])

    with pytest.raises(ai.AINoUsableCards):
        ai.generate_cards("topic", 3)

    assert client.messages.calls == 2


def test_no_key_raises_not_configured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ai.AINotConfigured):
        ai.generate_cards("topic", 1)


# --- HTTP integration (routing) --------------------------------------------


def test_generate_endpoint_returns_cards_and_usage(client, monkeypatch):
    from app import ai as ai_module
    from app.models import CostInfo

    canned = [{"front": "rojo", "back": "red"}, {"front": "azul", "back": "blue"}]
    usage = CostInfo(
        model="claude-haiku-4-5-20251001",
        input_tokens=250,
        output_tokens=400,
        cost_usd=0.0023,
    )
    monkeypatch.setattr(ai_module, "generate_cards", lambda topic, n: (canned, usage))

    res = client.post("/decks/1/generate", json={"topic": "colors", "count": 2})
    assert res.status_code == 200
    body = res.json()
    assert [{"front": c["front"], "back": c["back"]} for c in body["cards"]] == canned
    assert body["usage"]["cost_usd"] == 0.0023
    assert body["usage"]["input_tokens"] == 250

    # The drafted cards are persisted to the deck.
    deck = client.get("/decks/1").json()
    fronts = [c["front"] for c in deck["cards"]]
    assert "rojo" in fronts and "azul" in fronts


def test_no_usable_cards_returns_502(client, monkeypatch):
    from app import ai as ai_module

    def boom(topic, n):
        raise ai_module.AINoUsableCards("AI returned no usable cards")

    monkeypatch.setattr(ai_module, "generate_cards", boom)

    res = client.post("/decks/1/generate", json={"topic": "colors", "count": 2})
    assert res.status_code == 502
    assert res.json()["detail"] == "AI returned no usable cards"


@pytest.mark.parametrize(
    "payload",
    [
        {"topic": "colors", "count": 0},     # count too low
        {"topic": "colors", "count": 21},    # count too high
        {"topic": "", "count": 3},           # empty topic
        {"topic": "   ", "count": 3},        # whitespace-only topic
        {"topic": "x" * 201, "count": 3},    # topic too long
    ],
)
def test_bad_input_returns_422(client, payload):
    res = client.post("/decks/1/generate", json=payload)
    assert res.status_code == 422
