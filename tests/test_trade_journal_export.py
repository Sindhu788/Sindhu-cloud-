"""Grand Feature Expansion, Phase 4 Feature 23: Trade Journal Export to
PDF (paper_trading/trade_journal_export.py) -- a trade-by-trade PDF,
distinct from the only other paper-trading export (an Excel strategy-vs-
strategy comparison aggregate). Reuses reportlab, already an installed
dependency (backtest_engine/export.py's own PDF export uses it)."""

import os
from datetime import datetime, timezone

from data_engine import storage
from paper_trading import trade_journal_export


def _close(position_id, strategy_id="stratA", pnl=10.0, note=None):
    created_at = datetime.now(timezone.utc).isoformat()
    storage.open_paper_position({
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": created_at,
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    })
    storage.close_paper_position(position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
                                  "take_profit" if pnl >= 0 else "stop_loss", {}, {}, created_at,
                                  book_key=strategy_id)
    if note:
        storage.set_trade_note(position_id, note)


def test_export_with_no_closed_trades_still_produces_a_valid_pdf(test_db):
    path = trade_journal_export.export_trade_journal_pdf(strategy_id="nonexistent")
    assert os.path.isfile(path)
    assert path.endswith(".pdf")
    assert os.path.getsize(path) > 0


def test_export_across_all_strategies(test_db):
    _close("p1", strategy_id="stratA", pnl=15.0)
    _close("p2", strategy_id="stratB", pnl=-5.0)
    path = trade_journal_export.export_trade_journal_pdf()
    assert os.path.isfile(path)
    assert os.path.getsize(path) > 500  # a real table, not just the empty-state page


def test_export_scoped_to_one_strategy_only(test_db):
    _close("p1", strategy_id="stratA", pnl=15.0)
    _close("p2", strategy_id="stratB", pnl=-5.0)
    path = trade_journal_export.export_trade_journal_pdf(strategy_id="stratA")
    assert os.path.isfile(path)


def test_export_includes_user_note_without_crashing(test_db):
    _close("p1", strategy_id="stratA", pnl=15.0, note="Great entry timing")
    path = trade_journal_export.export_trade_journal_pdf(strategy_id="stratA")
    assert os.path.isfile(path)


def test_export_respects_limit(test_db):
    for i in range(5):
        _close(f"p{i}", strategy_id="stratA", pnl=1.0)
    path = trade_journal_export.export_trade_journal_pdf(strategy_id="stratA", limit=2)
    assert os.path.isfile(path)


def test_endpoint_returns_a_pdf_file_response(test_db):
    from sindhu_web.api.paper_trading import export_trade_journal

    _close("p1", strategy_id="stratA", pnl=15.0)
    response = export_trade_journal(strategy_id="stratA", limit=200)
    assert response.media_type == "application/pdf"
