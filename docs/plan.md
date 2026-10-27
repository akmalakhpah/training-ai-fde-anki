# Plan: Harden the `/generate` card generator

Week-4 AI FDE project. Take the one Claude-powered feature in this repo —
`POST /decks/{id}/generate` ([app/ai.py](../app/ai.py)) — and make it
production-shaped: reliable structured JSON, graceful handling of bad input,
self-reported cost per call, and a retry/fallback for malformed responses.

This `plan.md` is also the brief handed to Claude Code to do the work.

## Why `/generate` (not a new `/tag`)

The brief allows either hardening `/generate` or adding a `/tag` endpoint. We
harden `/generate` because it is the repo's *existing* Claude feature, already
uses tool-use for structured output (a good foundation), and is wired through
the real request layers (`routes → ai → db`). Hardening it exercises every
requirement on the checklist without inventing a parallel feature.

## Goal

Given a `topic` and `count`, return exactly `count` well-formed flashcards as
validated structured JSON, **plus** the cost of the call. The endpoint must:

- never 500 on bad or surprising input — it validates and returns a clean 4xx,
- never return half-formed cards — every card has a non-empty `front` and `back`,
- report tokens-in, tokens-out, and dollars for the call, read from
  `response.usage`,
- retry once and then fall back cleanly when the model returns nothing usable,
- keep working with no API key for every *other* endpoint (preserve the lazy
  import + `AINotConfigured → 503` contract).

## Output schema

We define the schema we conform to, in two layers.

**1. The tool Claude must call** (forced, `strict: true` so the input is
guaranteed to validate against the schema — supported on Haiku 4.5):

```jsonc
{
  "name": "save_cards",
  "strict": true,
  "input_schema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["cards"],
    "properties": {
      "cards": {
        "type": "array",
        "items": {
          "type": "object",
          "additionalProperties": false,
          "required": ["front", "back"],
          "properties": {
            "front": { "type": "string" },
            "back":  { "type": "string" }
          }
        }
      }
    }
  }
}
```

**2. The HTTP response** (new Pydantic models in [app/models.py](../app/models.py)).
Today the route returns a bare `list[CardDraft]`; we wrap it so cost rides
alongside the data:

```python
class CostInfo(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float          # rounded to 6 dp

class GenerateResponse(BaseModel):
    cards: list[Card]        # the inserted cards (with ids/scheduling)
    usage: CostInfo
```

`GenerateRequest` gains validation (see Failure modes): `topic` non-empty after
strip, `count` bounded `1..20`.

## Prompt versions

We iterate the prompt across two versions and keep both in the file/PR so the
change is reviewable.

**v1 (current, in `ai.py` today)** — single user turn:

> `Create exactly {n} flashcards to study the topic: {topic}. Each card has a
> concise front (a question or term) and a back (the answer). Save them with
> the save_cards tool.`

Weaknesses: no role/system framing; no guidance for ambiguous/empty/garbage
topics; no anti-duplication or length guidance; relies on the model to "just
call the tool."

**v2 (target)** — add a system prompt and tighten the user turn:

- *System:* "You are a flashcard author. You always produce exactly the
  requested number of cards and you always return them via the `save_cards`
  tool — never as prose. Keep each `front` a single question or term and each
  `back` a concise answer. Do not produce duplicate cards. If the topic is too
  vague to study, produce the best general-knowledge cards you can rather than
  refusing."
- *User:* the v1 instruction, plus "Return exactly {n} cards, no more, no less."
- Keep `tool_choice` forced to `save_cards`.

We record what changed and why in the PR description (per the brief).

## Failure modes (and what catches each)

| Input / event | Failure if unhandled | What catches it |
|---|---|---|
| `topic` empty / whitespace | API call on garbage; vague output | `GenerateRequest` validator: `min_length`/strip → **422** before any API call |
| `count <= 0` or huge (`500`) | infinite/garbage output, runaway cost | `count` bounded `1..20` (Pydantic `Field(ge=1, le=20)`) → **422** |
| very long / injection-y `topic` | token blowup, prompt steering | length cap on `topic` (e.g. ≤ 200 chars) → **422** |
| model returns no `tool_use` block | `[]` returned silently / `KeyError` | detect missing tool block → **retry once** with v2 nudge → fall back to **502** |
| model returns a card missing `front`/`back` | corrupt card inserted into DB | per-card validation; drop invalid cards; if none survive → retry → **502** |
| model returns ≠ `count` cards | wrong-size deck | accept what validates, log the mismatch (don't fail the user); count surfaced in logs |
| `429` / `5xx` from API | crash / user-facing 500 | SDK auto-retry (`max_retries`) + our one app-level retry → **502** on exhaustion |
| no `ANTHROPIC_API_KEY` | import error / 500 on core paths | preserve lazy import + `AINotConfigured → 503` (unchanged) |

**Retry/fallback shape:** one application-level retry. First attempt uses v2.
If the response has no usable cards (no tool block, or every card fails
validation), retry once. If the retry also yields nothing usable, raise a clean
**502** ("AI returned no usable cards") — we never insert junk and never 500.
The SDK's built-in `max_retries` handles transient `429`/`5xx` underneath this.

**Reliability check (one line for submission):** *An input like `count=500` or
an empty `topic` would make the feature emit malformed or garbage output —
caught by `GenerateRequest` field validation (count bounded 1–20, topic
non-empty) before the API call, with per-card schema validation dropping any
card missing a `front`/`back` after it.*

## Cost target

Cost is read from `response.usage` (`input_tokens`, `output_tokens`) and priced
from a small per-model rate table (USD per 1M tokens):

| Model | $/1M in | $/1M out |
|---|---|---|
| Claude Haiku 4.5 (`claude-haiku-4-5`) — **default** | $1.00 | $5.00 |
| Claude Sonnet 4.6 (`claude-sonnet-4-6`) — richer cards | $3.00 | $15.00 |

`cost_usd = input_tokens/1e6 * in_rate + output_tokens/1e6 * out_rate`

Estimated per-call cost for a typical `count=5` request (~250 input tokens incl.
tool schema, ~400 output tokens):

| Tier | in | out | **per-call** |
|---|---|---|---|
| Haiku 4.5 | $0.00025 | $0.0020 | **≈ $0.0023** (~0.2¢) |
| Sonnet 4.6 | $0.00075 | $0.0060 | **≈ $0.0068** (~0.7¢) |

**Target: under ~$0.005/call on the default (Haiku) tier.** What drives cost:
output tokens dominate, and they scale with `count` (more cards → more output) —
so the bounded `count` is also a cost guardrail. Input is nearly fixed (small
prompt + tool schema). The two model tiers above are the required cost note.

## Implementation steps

1. Add `CostInfo` / `GenerateResponse` to `models.py`; add validators to
   `GenerateRequest` (`count` 1–20, `topic` non-empty, length cap).
2. In `ai.py`: keep forced tool-use, add `strict: true` + system prompt (v2),
   add per-card validation, the one-retry loop, and a `usage`/cost helper with
   the rate table. Return `(cards, CostInfo)` from `generate_cards`.
3. In `routes.py`: map validation to 422 (FastAPI does this for the model),
   keep `AINotConfigured → 503`, add `→ 502` for "no usable cards", return
   `GenerateResponse`.
4. Tests (`tests/test_ai.py`, mocked — no network, no key): well-formed
   response → cards + cost; malformed first response then good retry; both
   malformed → 502; bad input (`count=0`, empty topic) → 422; cost math.
5. Open a PR; PR body records the v1→v2 prompt change and the per-call cost for
   both tiers.

## Deliverables

- Merged/open PR with the hardened feature + its test.
- This `docs/plan.md`.
- Cost note: per-call cost for Haiku 4.5 and Sonnet 4.6 (table above) and what
  drives it (output tokens, scaling with `count`).

## Stretch (optional)

- Prompt caching on the (now stable) system prompt + tool schema, and/or
  measure Haiku-vs-Sonnet cost delta on the same inputs.
