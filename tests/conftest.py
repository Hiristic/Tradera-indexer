"""Shared pytest fixtures."""
from __future__ import annotations

import pytest

from tradera_indexer.config import Config
from tradera_indexer.database import Database


@pytest.fixture()
def config(tmp_path) -> Config:
    """A Config object that uses a temporary database path."""
    return Config(
        app_id=12345,
        app_key="test-key",
        user_token="test-token",
        user_id=99,
        db_path=str(tmp_path / "test.db"),
    )


@pytest.fixture()
def db(config) -> Database:
    """An open in-memory-ish database (temporary file)."""
    database = Database(config.db_path)
    database.connect()
    yield database
    database.close()
