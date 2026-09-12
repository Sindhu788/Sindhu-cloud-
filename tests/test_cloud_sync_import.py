"""Cloud-to-local import (paper_trading/cloud_sync_import.py): completes
paper_trading/cloud_sync.py's previously one-way backup. See that
module's docstring for exactly what is and isn't merged, and why.
"""
from data_engine import db_backend, storage
from paper_trading import cloud_sync_import


def _closed_pos(pid, pnl=10.0, strategy_id="strat1"):
    return {
        "id": pid, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "exit_price": 101.0, "size": 1.0, "risk_amount": 10.0,
        "entry_time": 1000, "exit_time": 2000, "pnl": pnl, "pnl_pct": 1.0,
        "exit_reason": "take_profit", "entry_reason": "test", "strategy_id": strategy_id,
        "strategy_name": "Strat One", "strategy_version": 1, "lesson_ids": [], "confidence": 0.8,
        "market_snapshot": {}, "tags": [], "session": "london", "timeframe": "1h",
        "market_state": "trending", "lifecycle": {}, "reflection": None,
        "created_at": "2026-09-01T00:00:00+00:00", "closed_at": "2026-09-01T01:00:00+00:00",
        "lowest_price_seen": 99.0, "highest_price_seen": 101.5, "user_note": None,
    }


def _open_pos(pid):
    p = _closed_pos(pid)
    p["exit_price"] = None
    p["pnl"] = None
    p["closed_at"] = None
    return p


def test_import_merges_new_closed_positions(test_db):
    snapshot = {"generated_at": "2026-09-12T00:00:00+00:00",
                "closed_positions": [_closed_pos("imp001"), _closed_pos("imp002")],
                "open_positions": []}
    result = cloud_sync_import.import_snapshot(snapshot)
    assert result["ok"] is True
    assert result["closed_positions_imported"] == 2
    assert result["closed_positions_already_present"] == 0
    assert storage.get_paper_position("imp001")["status"] == "closed"
    assert storage.get_paper_position("imp001")["pnl"] == 10.0


def test_import_is_idempotent_no_duplicates_no_double_counted_pnl(test_db):
    snapshot = {"generated_at": "2026-09-12T00:00:00+00:00",
                "closed_positions": [_closed_pos("imp003", pnl=25.0, strategy_id="stratX")],
                "open_positions": []}
    before = storage.get_paper_realized_pnl_total("stratX")
    r1 = cloud_sync_import.import_snapshot(snapshot)
    r2 = cloud_sync_import.import_snapshot(snapshot)
    assert r1["closed_positions_imported"] == 1
    assert r2["closed_positions_imported"] == 0
    assert r2["closed_positions_already_present"] == 1
    after = storage.get_paper_realized_pnl_total("stratX")
    assert after - before == 25.0  # not 50.0 -- imported exactly once


def test_open_positions_are_never_merged_into_local_table(test_db):
    snapshot = {"generated_at": "2026-09-12T00:00:00+00:00",
                "closed_positions": [], "open_positions": [_open_pos("imp004")]}
    result = cloud_sync_import.import_snapshot(snapshot)
    assert result["open_positions_skipped"] == 1
    assert storage.get_paper_position("imp004") is None


def test_refuses_a_malformed_snapshot(test_db):
    result = cloud_sync_import.import_snapshot({"not_a_snapshot": True})
    assert result["ok"] is False


def test_refuses_to_run_on_a_cloud_deployment(test_db, monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    snapshot = {"generated_at": "now", "closed_positions": [_closed_pos("imp005")], "open_positions": []}
    result = cloud_sync_import.import_snapshot(snapshot)
    assert result["ok"] is False
    monkeypatch.setattr(db_backend, "IS_POSTGRES", False)
    assert storage.get_paper_position("imp005") is None
