"""Shared pytest fixtures. Every test in this suite runs against a fresh,
isolated SQLite database (a temp file, schema created fresh via
storage.init_db()) instead of the real data/database/sindhu.db -- these
are regression tests for application behavior, not a place to read or
write real trading data.
"""

import pytest

from data_engine import storage


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_sindhu.db"
    monkeypatch.setattr(storage, "DB_PATH", str(db_path))
    storage.init_db()
    yield str(db_path)
