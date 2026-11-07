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

# Strategy library: tests work on a throw-away COPY so nothing ever rewrites the git-tracked
# strategies/library/*/meta.json (the strategy list endpoint refreshes backtest_snapshot on read).
if not os.environ.get("SINDHU_STRATEGY_LIBRARY_DIR"):
    _real_lib = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strategies", "library")
    _test_lib = tempfile.mkdtemp(prefix="sindhu_test_library_")
    shutil.copytree(_real_lib, _test_lib, dirs_exist_ok=True)
    os.environ["SINDHU_STRATEGY_LIBRARY_DIR"] = _test_lib
    atexit.register(shutil.rmtree, _test_lib, ignore_errors=True)

# Tests run as the "main" process role; the public-signal-owner guard defaults to
# "cloud", so declare this process the publisher unless a test overrides it.
os.environ.setdefault("SINDHU_PUBLIC_SIGNAL_OWNER", "main")

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


@pytest.fixture(autouse=True)
def _reset_db_connect_breaker():
    """Master plan A6: the Postgres connect breaker is process-global; a test that simulates an outage must not leak it into the next."""
    from data_engine import db_backend
    db_backend.reset_breaker()
    yield
    db_backend.reset_breaker()


@pytest.fixture(autouse=True)
def _public_signals_allowed_in_gate_tests(monkeypatch):
    """Master plan A14: automatic public signals are OFF by code default (SINDHU_PUBLIC_SIGNALS unset). The existing gate tests check
    what happens once the owner has turned them on, so they run with it set; tests of the default itself delete it explicitly
    (tests/test_public_signals_default_off.py)."""
    monkeypatch.setenv("SINDHU_PUBLIC_SIGNALS", "1")
    yield


@pytest.fixture(autouse=True)
def _isolated_coingecko_disk_cache(monkeypatch, tmp_path):
    """Master plan V2 R1: the last-good top-coins list on disk must not leak between tests."""
    try:
        from data_engine import coingecko_client as _cg
        monkeypatch.setattr(_cg, "_disk_cache_path", lambda: str(tmp_path / "coingecko_top_coins_cache.json"))
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    """Master plan V2 LG4: per-IP and per-username login throttles are in memory; tests must not inherit them."""
    try:
        from sindhu_web.api import auth as _auth_api
        _auth_api._fails.clear()
        _auth_api._user_fails.clear()
    except Exception:
        pass
    yield
