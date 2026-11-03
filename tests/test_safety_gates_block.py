"""Phase 13: trigger each safety gate and confirm it blocks. Guards against any gate being weakened."""
import time

from data_engine import storage
from paper_trading import (account_drawdown_guard, auto_downgrade, kill_switch, pattern_stats,
                           risk_manager, telegram_bot)
from paper_trading import config as pt_config


def _settings(**over):
    return dict(pt_config.defaults(), **over)


def _open_position(symbol, book="s1"):
    with storage.get_conn() as c:
        c.execute("INSERT INTO paper_positions (exchange, symbol, direction, entry_price, stop_loss, take_profit, size, "
                  "risk_amount, entry_time, strategy_id, status, created_at) VALUES "
                  "('bybit', ?, 'long', 1, 0.9, 1.2, 1, 1, 1, ?, 'open', '2026-01-01')", (symbol, book))


def test_kill_switch_blocks_new_trades(test_db):
    kill_switch.activate(reason="test", actor="test", close_positions=False)
    ok, reason, _, _ = risk_manager.evaluate("s1", "BTCUSDT", {}, _settings())
    assert ok is False and "KILL SWITCH" in reason


def test_account_drawdown_breaker_blocks_new_trades(test_db, monkeypatch):
    monkeypatch.setattr(account_drawdown_guard, "is_globally_paused", lambda: True)
    ok, reason, _, _ = risk_manager.evaluate("s1", "BTCUSDT", {}, _settings())
    assert ok is False and "drawdown circuit-breaker" in reason


def test_max_five_distinct_coins_per_strategy(test_db):
    assert pt_config.defaults()["max_open_trades"] == 5
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"):
        _open_position(sym)
    ok, reason, _, _ = risk_manager.evaluate("s1", "DOGEUSDT", {}, _settings())
    assert ok is False and "max coins for this strategy reached (5)" in reason


def test_signal_freshness_window_is_15_minutes_and_drift_half_a_percent(monkeypatch):
    monkeypatch.setattr(telegram_bot, "load_settings", lambda: dict(telegram_bot._DEFAULTS))
    now = int(time.time() * 1000)
    old = {"entry_time": now - 16 * 60_000, "entry_price": 100.0}
    fresh = {"entry_time": now - 14 * 60_000, "entry_price": 100.0}
    assert telegram_bot.is_signal_stale(old, now_ms=now) is True
    assert telegram_bot.is_signal_stale(fresh, now_ms=now) is False
    assert telegram_bot.price_has_moved_away(fresh, 100.6) is True
    assert telegram_bot.price_has_moved_away(fresh, 100.4) is False


def test_wilson_25_trade_gate_and_evolution_100_trade_gate_are_unchanged():
    assert pattern_stats.MIN_SAMPLE_SIZE == 25
    assert pattern_stats.classify(24, 24)["reliable"] is False      # 24 trades: no conclusion
    assert pattern_stats.classify(25, 25)["reliable"] is True       # 25 trades: first conclusion
    assert auto_downgrade.MIN_TRADES_FOR_EVALUATION == 100
