"""Urgent bug fix, 2026-09-09: GET /api/paper-trading/decisions timed out
(15000ms) once "Enable All for Paper Trading" brought 75 strategies
online and they started generating real trades. Root cause:
storage.log_paper_decision() opened a brand-new Postgres connection AND
ran a full-table prune query (`DELETE ... WHERE id NOT IN (SELECT id ...
ORDER BY id DESC LIMIT 2000)`) on EVERY call, and paper_trading.engine
called it once per candidate evaluated per coin per tick -- with 75
strategies enabled, a single tick could fire this hundreds of times,
starving concurrent dashboard requests (the plain, already-indexed
/decisions SELECT included) of their share of Postgres's unpooled
connections while the prune query churned.

Fix: engine._log_decision() now buffers into self._pending_decisions and
_flush_decisions() writes the whole batch in ONE connection (one
executemany insert + ONE prune, not one prune per row) at the end of
each tick / manual scan.
"""
from datetime import datetime, timezone

import pytest

from data_engine import storage
from paper_trading.engine import PaperTradingEngine


def _entry(**overrides):
    e = {
        "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "decision": "rejected", "reason": "test", "strategy_id": "strat1",
        "strategy_name": "Test Strategy", "lesson_ids": [], "confidence": 0.5,
        "market_state": "trending", "session": "london", "timeframe": "5m",
        "position_id": None, "market_snapshot": {"price": 100.0},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    e.update(overrides)
    return e


def test_batch_writes_every_entry_in_one_connection(test_db, monkeypatch):
    call_count = {"n": 0}
    real_get_conn = storage.get_conn

    def counting_get_conn():
        call_count["n"] += 1
        return real_get_conn()

    monkeypatch.setattr(storage, "get_conn", counting_get_conn)
    storage.log_paper_decisions_batch([_entry(symbol=f"COIN{i}USDT") for i in range(50)])

    assert call_count["n"] == 1
    decisions = storage.list_paper_decisions(limit=100)
    assert len(decisions) == 50


def test_batch_of_empty_list_opens_no_connection(test_db, monkeypatch):
    call_count = {"n": 0}
    real_get_conn = storage.get_conn

    def counting_get_conn():
        call_count["n"] += 1
        return real_get_conn()

    monkeypatch.setattr(storage, "get_conn", counting_get_conn)
    storage.log_paper_decisions_batch([])

    assert call_count["n"] == 0


def test_batch_still_prunes_down_to_2000_rows(test_db):
    storage.log_paper_decisions_batch([_entry(symbol=f"COIN{i}USDT") for i in range(2050)])
    decisions = storage.list_paper_decisions(limit=5000)
    assert len(decisions) == 2000


@pytest.fixture
def isolated_engine():
    return PaperTradingEngine()


def test_engine_buffers_decisions_instead_of_writing_immediately(test_db, monkeypatch, isolated_engine):
    monkeypatch.setattr(storage, "log_paper_decisions_batch",
                         lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called yet")))
    isolated_engine._log_decision("binance", "BTCUSDT", {"strategy_id": "strat1"},
                                   "rejected", "test", {"market_state": "trending"})
    assert len(isolated_engine._pending_decisions) == 1


def test_flush_writes_the_whole_buffer_in_one_call_and_clears_it(test_db, monkeypatch, isolated_engine):
    calls = []
    monkeypatch.setattr(storage, "log_paper_decisions_batch", lambda entries: calls.append(list(entries)))

    for i in range(10):
        isolated_engine._log_decision("binance", f"COIN{i}USDT", {"strategy_id": "strat1"},
                                       "rejected", "test", {"market_state": "trending"})
    isolated_engine._flush_decisions()

    assert len(calls) == 1
    assert len(calls[0]) == 10
    assert isolated_engine._pending_decisions == []


def test_flush_with_nothing_pending_does_not_open_a_connection(test_db, monkeypatch, isolated_engine):
    monkeypatch.setattr(storage, "log_paper_decisions_batch",
                         lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")))
    isolated_engine._flush_decisions()  # no-op, buffer is empty


def test_flush_clears_buffer_even_if_the_write_fails(test_db, monkeypatch, isolated_engine):
    """A logging failure must never repeat forever or silently drop the
    NEXT tick's decisions into the same failed batch."""
    monkeypatch.setattr(storage, "log_paper_decisions_batch",
                         lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db unreachable")))
    isolated_engine._log_decision("binance", "BTCUSDT", {"strategy_id": "strat1"},
                                   "rejected", "test", {"market_state": "trending"})

    isolated_engine._flush_decisions()  # must not raise

    assert isolated_engine._pending_decisions == []
