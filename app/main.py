"""FastAPI application entry point.

On startup it initializes the SQLite schema and seeds sample data if the database
is empty. Run it with::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import db, seed
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    seed.seed_if_empty()
    yield


app = FastAPI(title="AI Anki", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/")
def root() -> dict:
    return {
        "name": "AI Anki",
        "docs": "/docs",
        "decks": "/decks/{id}",
    }
