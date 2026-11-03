"""Shared pytest fixtures. Every test in this suite runs against a fresh,
isolated SQLite database (a temp file, schema created fresh via
storage.init_db()) instead of the real data/database/sindhu.db -- these
are regression tests for application behavior, not a place to read or
write real trading data.
"""

import atexit
import os
import shutil
import tempfile

# Hermetic data directory: tests must never depend on (or touch) the
# developer's real data/config, data/database/sindhu.db or auth files. This
# must run before any SINDHU module computes DATA_DIR at import time.
if not os.environ.get("SINDHU_DATA_DIR"):
    _TEST_DATA_DIR = tempfile.mkdtemp(prefix="sindhu_test_data_")
    os.environ["SINDHU_DATA_DIR"] = _TEST_DATA_DIR
    atexit.register(shutil.rmtree, _TEST_DATA_DIR, ignore_errors=True)

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


@pytest.fixture(scope="session", autouse=True)
def _initialise_hermetic_database():
    """Create the schema once in the temp data dir so tests that call storage
    directly (without the per-test ``test_db`` fixture) do not hit a missing
    table."""
    storage.init_db()
    yield
