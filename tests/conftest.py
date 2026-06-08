"""Shared test fixtures.

Each test gets a fresh SQLite database in a temp directory (via ANKI_DB_PATH) and a
FastAPI TestClient. Entering the TestClient context fires the startup event, which
initializes the schema and seeds the sample data.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANKI_DB_PATH", str(tmp_path / "test.db"))
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
