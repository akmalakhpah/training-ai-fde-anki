# AI Anki

This is the **Week 1 training repo** for the [AI Forward Deployed Engineer (FDE)
Training](https://akmalakhpah.github.io/training-ai-fde/) — a 12-week course on
taking AI features from coursework to production. The course site is where the full
curriculum, schedule, and the complete Week 1 brief and assessment live.

## What AI Anki is

AI Anki is a small [FastAPI](https://fastapi.tiangolo.com/) flashcard study app with
spaced repetition: you create decks, add cards, study the cards that are **due**, and
rate your recall so a simplified schedule decides when each card comes back. One
endpoint uses Claude to draft flashcards from a topic you give it. Data lives in a
local SQLite file, so it runs with zero setup.

It is intentionally a **teaching** repo — kept small and production-*shaped* rather
than production-complete. It ships with a couple of rough edges on purpose; finding
and fixing them is the Week 1 project (see below).

## For students (the Week 1 project)

You do all your work on **your own fork**, never on the canonical repo:

1. **Fork** [`akmalakhpah/training-ai-fde-anki`](https://github.com/akmalakhpah/training-ai-fde-anki)
   to your own GitHub account.
2. **Clone your fork** and work on a branch.
3. **Open a pull request into your own fork's `main`**, and get it merged with CI
   green.

The goal is to fix one bug by hand (reading the code and the stack trace yourself),
fix a second with Claude Code (briefing it and reviewing its diff), and write the
repo's `CLAUDE.md`. The full brief and assessment are on the
[course site](https://akmalakhpah.github.io/training-ai-fde/).

## Requirements

- Python 3.12+

## Install

```bash
pip install -e .
```

## Run

```bash
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000 for a simple web UI (create decks, add cards, study,
view stats, and generate cards). The interactive API docs are at
http://127.0.0.1:8000/docs. On first run the app creates `anki.db` and seeds a couple
of sample decks.

### Using the API

```bash
# Create a deck
curl -X POST http://127.0.0.1:8000/decks \
  -H "Content-Type: application/json" \
  -d '{"name": "French Basics"}'

# Add a card to deck 1
curl -X POST http://127.0.0.1:8000/decks/1/cards \
  -H "Content-Type: application/json" \
  -d '{"front": "bonjour", "back": "hello"}'

# Review a card (rating: again | hard | good | easy)
curl -X POST http://127.0.0.1:8000/cards/1/review \
  -H "Content-Type: application/json" \
  -d '{"rating": "good"}'

# Deck stats
curl http://127.0.0.1:8000/decks/1/stats
```

## Run the tests

```bash
pytest
```

The suite runs with no API key and makes no network calls (the Claude endpoint is
mocked in tests).

## Continuous integration (CI)

GitHub Actions runs the test suite on every push and pull request. The workflow is
[.github/workflows/ci.yml](.github/workflows/ci.yml): it checks out the code, sets up
Python 3.12, runs `pip install -e .`, and runs `pytest` — no API key required.

In the Week 1 project you'll see this in action: add a failing test for a bug *before*
fixing it and CI goes red, then push the fix and watch it go green.

## API-key setup (optional)

Everything above works without an API key. Only the `POST /decks/{id}/generate`
endpoint calls Claude; without a key it returns a clean `503` and the rest of the
app is unaffected. To enable it:

```bash
cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY=your-key
```

Get an API key from the Claude Console:
**https://platform.claude.com/settings/workspaces/default/keys**

The endpoint defaults to Claude Haiku 4.5 (cheap and fast for card generation); you
can bump it to Sonnet in [app/ai.py](app/ai.py) for richer cards.
