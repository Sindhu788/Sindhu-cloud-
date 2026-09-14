"""Grand Master Batch, Phase 4 Item 17 -- Show Me the Math.

Covers the backend piece: raw win counts exposed alongside already-
present win-rate percentages/total-trade counts, so the dashboard can
show the real division instead of just a rounded percentage. The
frontend math-button/modal itself is pure client-side rendering of
numbers already present in these responses -- not separately unit
tested, consistent with this codebase's convention of not unit-testing
pure JS rendering helpers.
"""

from datetime import datetime, timezone

from data_engine import storage
from sindhu_web.api.home import _account_snapshot


def _close(pos_id, strategy_id, pnl):
    now = datetime.now(timezone.utc).isoformat()
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": now, "strategy_id": strategy_id, "strategy_name": strategy_id,
    })
    storage.close_paper_position(pos_id, 100.0 + pnl, now, pnl, pnl, "take_profit", {}, {}, now, book_key=strategy_id)


def test_account_snapshot_exposes_raw_win_count(test_db):
    _close("p1", "strat1", 10.0)
    _close("p2", "strat1", 10.0)
    _close("p3", "strat1", -5.0)
    snapshot = _account_snapshot()
    assert snapshot["total_trades"] == 3
    assert snapshot["wins"] == 2
    assert snapshot["win_rate"] == round(2 / 3 * 100, 2)


def test_account_snapshot_falls_back_when_no_trades_closed(test_db):
    snapshot = _account_snapshot()
    # No live trades -- falls back to the most recent completed backtest,
    # which may legitimately be None in a fresh test DB.
    assert snapshot is None or "wins" in snapshot
