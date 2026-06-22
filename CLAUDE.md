# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

AI Anki is a small FastAPI flashcard app with spaced repetition and one Claude-powered
endpoint. It is the **Week 1 training repo** for the AI FDE course — a *teaching* repo,
kept production-*shaped* rather than production-complete. It intentionally ships with a
couple of planted bugs; finding and fixing them is the student project. Be aware of this
when reviewing code: a discoverable bug may be deliberate, so confirm intent before
"fixing" something unasked.

## Commands

```bash
pip install -e .                      # install (editable) — pulls deps from pyproject.toml
uvicorn app.main:app --reload         # run the app at http://127.0.0.1:8000 (UI at /, API docs at /docs)
pytest                                # run the full test suite
pytest tests/test_services.py         # run one test file
pytest tests/test_services.py::test_name -v   # run a single test
```

Tests run with no API key and make no network calls — the Claude endpoint is mocked.
CI (`.github/workflows/ci.yml`) runs `pip install -e .` then `pytest` on every push and PR.

## Architecture

Requests flow through strict layers, each in its own module under `app/`:

```
routes.py  →  services.py  →  db.py  →  SQLite (anki.db)
  (HTTP)       (logic)         (data)
   ↑ models.py (Pydantic in/out)      ↑ ai.py (Claude, called from routes)
```

- **`routes.py`** — FastAPI endpoints. Each route does validation/404 checks, then
  delegates: business logic to `services.py`, raw data access to `db.py`. Keep routes thin.
- **`services.py`** — spaced-repetition scheduling, due checks, and stats. The
  schedule lives in `schedule_next()` (rating → new interval/ease); `EASE_FLOOR = 1.3`.
- **`db.py`** — the *only* place that touches SQLite. Every function opens its own
  connection via `connect()`. Returns plain `dict`s, not rows.
- **`models.py`** — Pydantic request/response models; the serialization boundary.
- **`ai.py`** — the `POST /decks/{id}/generate` feature. Uses the Anthropic SDK with
  **tool use** for structured output (forces a `save_cards` tool call, reads cards from
  the tool input — no string parsing). Raises `AINotConfigured` when no key is set, which
  `routes.py` turns into a clean 503. The SDK is imported lazily inside `generate_cards`.
- **`main.py`** — app entry point. The `lifespan` handler runs `db.init_db()` then
  `seed.seed_if_empty()` on startup, so the schema and sample data exist on first run.

The data model is three tables (`decks`, `cards`, `reviews`) defined in `data/schema.sql`
and applied via `executescript` in `db.init_db()` — **edit the schema there**, not in code.

## Conventions that matter

- **Database path is env-driven.** `db.db_path()` reads `ANKI_DB_PATH` (default: `anki.db`
  in the repo root). Tests rely on this: `conftest.py` points each test at a fresh temp DB
  and enters a `TestClient` context (which fires startup → schema + seed). Don't hardcode
  the DB path.
- **The AI key is optional.** Everything except `/decks/{id}/generate` works with no
  `ANTHROPIC_API_KEY`. Preserve that — never make core paths import `anthropic` eagerly or
  require a key. Set the key in `.env` (see `.env.example`); `ai.py` calls `load_dotenv()`.
- **Model choice** lives in `ai.py` as `MODEL` (defaults to Claude Haiku 4.5 for cheap card
  generation; can be bumped to Sonnet).
- **`seed.py` is calibrated to the planted bugs** — it creates one card due yesterday and
  one due tomorrow, plus an empty deck, so the bugs are observable out of the box. If you
  change scheduling or stats logic, keep the seed meaningful.
