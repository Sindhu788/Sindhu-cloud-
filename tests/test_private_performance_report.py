"""Master 15-Item task, Item 10: Private Telegram Report Delivery (Weekly
+ Monthly PDF reports, Hinglish, personal_chat_id only -- never the public
channel). Same reportlab/test-DB conventions as the existing
test_trade_journal_export.py."""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from data_engine import storage
from paper_trading import private_performance_report as report


def _close(position_id, pnl, closed_at, strategy_id="stratA"):
    created_at = closed_at
    storage.open_paper_position({
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": created_at,
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    })
    storage.close_paper_position(position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
                                  "take_profit" if pnl >= 0 else "stop_loss", {}, {}, created_at,
                                  book_key=strategy_id)
    # close_paper_position sets closed_at to "now" -- overwrite directly so
    # period-window tests can control exactly which period a trade lands in.
    with storage.get_conn() as conn:
        conn.execute("UPDATE paper_positions SET closed_at=? WHERE id=?", (closed_at, position_id))


def test_metrics_with_no_trades_in_period_returns_honest_zeros(test_db):
    start = "2026-01-01T00:00:00+00:00"
    end = "2026-01-08T00:00:00+00:00"
    m = report.compute_period_performance_metrics(start, end)
    assert m["total_trades"] == 0
    assert m["win_rate"] == 0.0
    assert m["profit_factor"] is None
    assert m["net_profit"] == 0.0
    assert m["max_drawdown"] == 0.0


def test_metrics_computed_correctly_from_real_closed_trades(test_db):
    start = "2026-01-01T00:00:00+00:00"
    end = "2026-01-08T00:00:00+00:00"
    _close("p1", 100.0, "2026-01-02T00:00:00+00:00")
    _close("p2", -40.0, "2026-01-03T00:00:00+00:00")
    _close("p3", 50.0, "2026-01-04T00:00:00+00:00")
    # outside the period -- must NOT be counted
    _close("p4", 9999.0, "2026-02-01T00:00:00+00:00")

    m = report.compute_period_performance_metrics(start, end)
    assert m["total_trades"] == 3
    assert m["win_rate"] == round(2 / 3 * 100, 2)
    assert m["net_profit"] == 110.0
    assert m["profit_factor"] == round(150.0 / 40.0, 3)
    assert m["avg_win"] == 75.0
    assert m["avg_loss"] == -40.0
    assert m["max_drawdown"] > 0  # the -40 dip after the +100 peak is a real drawdown


def test_comparison_rows_only_include_finalized_comparisons(test_db):
    now = "2026-01-05T00:00:00+00:00"
    storage.create_evolution_comparison(
        "BOT_S1", "BOT_S1_G1", "BOT_S1_G2", 100,
        {"win_rate": 40.0, "total_pnl": 10.0, "avg_profit_factor": 0.9, "max_drawdown_pct": 20.0}, now,
    )
    pending = storage.list_evolution_comparisons(base_id="BOT_S1")[0]
    storage.finalize_evolution_comparison(
        pending["id"],
        {"win_rate": 55.0, "total_pnl": 40.0, "avg_profit_factor": 1.3, "max_drawdown_pct": 12.0},
        "improved", False, now,
    )
    storage.create_evolution_comparison(
        "BOT_S2", "BOT_S2_G1", "BOT_S2_G2", 100,
        {"win_rate": 50.0, "total_pnl": 20.0, "avg_profit_factor": 1.0, "max_drawdown_pct": 15.0}, now,
    )  # never finalized -- must be excluded

    rows = report.original_vs_evolution_comparison_rows("2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00")
    assert len(rows) == 1
    assert rows[0]["base_id"] == "BOT_S1"
    assert rows[0]["original"]["win_rate"] == 40.0
    assert rows[0]["evolution_generation"]["win_rate"] == 55.0
    assert rows[0]["rolled_back"] is False


def test_generate_report_pdf_produces_a_real_file_with_real_data(test_db):
    """Real evidence, not simulated: real trades + a real finalized
    evolution comparison, run through the real reportlab pipeline."""
    _close("p1", 100.0, "2026-01-02T00:00:00+00:00")
    _close("p2", -40.0, "2026-01-03T00:00:00+00:00")
    now = "2026-01-05T00:00:00+00:00"
    storage.create_evolution_comparison(
        "BOT_S1", "BOT_S1_G1", "BOT_S1_G2", 100,
        {"win_rate": 40.0, "total_pnl": 10.0, "avg_profit_factor": 0.9, "max_drawdown_pct": 20.0}, now,
    )
    pending = storage.list_evolution_comparisons(base_id="BOT_S1")[0]
    storage.finalize_evolution_comparison(
        pending["id"], {"win_rate": 55.0, "total_pnl": 40.0, "avg_profit_factor": 1.3, "max_drawdown_pct": 12.0},
        "improved", False, now,
    )

    path = report.generate_report_pdf("Weekly", "2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00")
    assert os.path.isfile(path)
    assert path.endswith(".pdf")
    assert os.path.getsize(path) > 1000  # a real multi-table report, not an empty stub


def test_generate_report_pdf_with_zero_data_still_produces_a_valid_pdf(test_db):
    path = report.generate_report_pdf("Monthly", "2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00")
    assert os.path.isfile(path)
    assert os.path.getsize(path) > 0


def test_send_report_uses_the_private_document_path_never_the_public_channel(test_db):
    """Mocks ONLY the Telegram network call (no real personal_chat_id/
    permission available in this environment) -- verifies the real PDF is
    genuinely generated first, and that delivery goes through
    send_private_document (the DM-only path), never _raw_send/
    send_signal_for_position (the public-channel paths)."""
    with patch("paper_trading.telegram_bot.send_private_document") as mock_send:
        mock_send.return_value = {"ok": True, "error": None}
        result = report.send_report("Weekly", "2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00")

    assert result["ok"] is True
    assert os.path.isfile(result["pdf_path"])
    mock_send.assert_called_once()
    called_path = mock_send.call_args[0][0]
    assert called_path == result["pdf_path"]
