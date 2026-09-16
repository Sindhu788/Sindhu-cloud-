"""Shared pytest fixtures. Every test in this suite runs against a fresh,
isolated SQLite database (a temp file, schema created fresh via
storage.init_db()) instead of the real data/database/sindhu.db -- these
are regression tests for application behavior, not a place to read or
write real trading data.
"""

import pytest

from data_engine import storage
from sindhu_web import cache


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_sindhu.db"
    monkeypatch.setattr(storage, "DB_PATH", str(db_path))
    # The in-memory endpoint cache is process-global: without clearing it, a
    # cached endpoint (e.g. /api/reports/best-worst/strategies) would serve
    # one test's fresh-DB result to the next test's different fresh DB.
    cache.clear_all()
    storage.init_db()
    yield str(db_path)
    cache.clear_all()
