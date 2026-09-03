"""Grand Feature Expansion, Phase 4 Feature 8: Trade Annotation --
data_engine.storage.set_trade_note() + sindhu_web/api/paper_trading.py's
POST /api/paper-trading/positions/{id}/note. A personal, user-written
note on one specific trade, distinct from reflection_json (fully
auto-generated/templated, never user-editable).
"""

import pytest
from fastapi import HTTPException

from data_engine import storage
from sindhu_web.api.paper_trading import TradeNoteRequest, set_trade_note as set_trade_note_endpoint


def _open(position_id, status="open"):
    storage.open_paper_position({
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })
    if status == "closed":
        storage.close_paper_position(position_id, 105.0, 1700000100000, 5.0, 5.0,
                                      "take_profit", {}, {}, "2026-01-02T00:00:00+00:00")


def test_new_position_has_no_note_by_default(test_db):
    _open("p1")
    assert storage.get_paper_position("p1")["user_note"] is None


def test_set_note_persists_on_an_open_position(test_db):
    _open("p1")
    storage.set_trade_note("p1", "Entered too early, ignored volume signal.")
    assert storage.get_paper_position("p1")["user_note"] == "Entered too early, ignored volume signal."


def test_set_note_works_on_a_closed_position_too(test_db):
    _open("p1", status="closed")
    storage.set_trade_note("p1", "Good discipline on the exit.")
    pos = storage.get_paper_position("p1")
    assert pos["user_note"] == "Good discipline on the exit."
    assert pos["status"] == "closed"


def test_setting_a_note_never_touches_pnl_or_other_fields(test_db):
    _open("p1", status="closed")
    before = storage.get_paper_position("p1")
    storage.set_trade_note("p1", "a note")
    after = storage.get_paper_position("p1")
    assert after["pnl"] == before["pnl"]
    assert after["exit_price"] == before["exit_price"]
    assert after["status"] == before["status"]


def test_note_can_be_cleared(test_db):
    _open("p1")
    storage.set_trade_note("p1", "temporary note")
    storage.set_trade_note("p1", "")
    assert storage.get_paper_position("p1")["user_note"] == ""


def test_endpoint_sets_a_note(test_db):
    _open("p1")
    result = set_trade_note_endpoint("p1", TradeNoteRequest(note="via the API"))
    assert result["ok"] is True
    assert storage.get_paper_position("p1")["user_note"] == "via the API"


def test_endpoint_404s_for_an_unknown_position(test_db):
    with pytest.raises(HTTPException) as exc:
        set_trade_note_endpoint("does-not-exist", TradeNoteRequest(note="x"))
    assert exc.value.status_code == 404
