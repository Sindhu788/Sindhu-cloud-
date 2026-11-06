"""Master plan A9-A13: MAIN_WALLET ($100 real-like paper wallet) rules, on the test SQLite database."""
import time

import pytest

from paper_trading import wallet


@pytest.fixture
def w(test_db, monkeypatch):
    wallet._reset_for_tests()
    from paper_trading import kill_switch, telegram_bot
    monkeypatch.setattr(kill_switch, "is_active", lambda: False)
    classes = {"rob": "ROBUST", "fra": "FRAGILE"}
    monkeypatch.setattr(telegram_bot, "validation_class", lambda sid: classes.get(sid, "FAILED"))
    wallet.ensure()
    yield wallet
    wallet._reset_for_tests()


_n = [0]


def pos(symbol="BTC/USDT", entry=100.0, stop=95.0, direction="long", strategy="s1", target=110.0):
    _n[0] += 1
    return {"id": f"r{_n[0]}", "symbol": symbol, "entry_price": entry, "stop_loss": stop, "take_profit": target, "direction": direction,
            "strategy_id": strategy, "strategy_name": strategy, "exchange": "okx", "timeframe": "1h", "confidence": 60}


def test_created_once_with_100_dollars(w):
    assert w.cash() == 100.0 and w.summary()["equity"] == 100.0
    w._reset_for_tests()
    w.ensure()                                            # idempotent: nothing changes the second time
    assert w.cash() == 100.0 and w._get("start_balance") == "100.00"


def test_risk_based_size_fees_and_slippage(w):
    w.offer(pos(entry=100.0, stop=95.0))
    d = w.settle()[0]
    assert d["decision"] == "opened"
    fill = 100.0 * 1.0005
    stop_dist = (fill - 95.0) / fill
    assert d["notional"] == pytest.approx(1.0 / stop_dist, rel=1e-9)     # 1 % of $100 equity at risk
    assert d["fee"] == pytest.approx(d["notional"] * 0.001)
    assert w.cash() == pytest.approx(100.0 - d["notional"] - d["fee"])


def test_below_min_notional_is_rejected_with_reason(w):
    w.offer(pos(entry=100.0, stop=50.0))                  # 1 % risk / 50 % stop distance = $2 < $5
    d = w.settle()[0]
    assert d["decision"] == "rejected" and "minimum notional" in d["reason"]
    assert w.journal(1)[0]["event"] == "reject"


def test_long_only_and_no_stop(w):
    w.offer(pos(direction="short", stop=105.0))
    w.offer(pos(stop=None))
    a, b = w.settle()
    assert "long-only" in a["reason"] and "stop-loss" in b["reason"]


def test_max_four_open_positions(w):
    for i in range(5):
        w.offer(pos(symbol=f"C{i}/USDT", entry=100.0, stop=90.0))
    out = w.settle()
    assert [o["decision"] for o in out] == ["opened"] * 4 + ["rejected"]
    assert "wallet full" in out[4]["reason"]


def test_duplicate_entry_guard_same_coin_and_direction_within_60_min(w):
    w.offer(pos(symbol="ETH/USDT", stop=90.0))
    assert w.settle()[0]["decision"] == "opened"
    w.offer(pos(symbol="ETH/USDT", stop=90.0))
    assert "duplicate" in w.settle()[0]["reason"]
    w.offer(pos(symbol="ETH/USDT", stop=90.0))
    assert w.settle(now=time.time() + 61 * 60)[0]["decision"] == "opened"


def test_priority_best_validation_class_first_then_first_come(w, monkeypatch):
    monkeypatch.setitem(wallet.DEFAULTS, "max_open_positions", 1)
    w.offer(pos(symbol="A/USDT", strategy="s_failed", stop=90.0))
    w.offer(pos(symbol="B/USDT", strategy="fra", stop=90.0))
    w.offer(pos(symbol="C/USDT", strategy="rob", stop=90.0))
    out = w.settle()
    assert out[0]["decision"] == "opened" and w.open_positions()[0]["symbol"] == "C/USDT"
    assert [o["decision"] for o in out[1:]] == ["rejected", "rejected"]


def test_exit_mirrors_research_close_and_reconciles_to_the_cent(w):
    r = pos(entry=100.0, stop=95.0)
    w.offer(r)
    w.settle()
    w.mark("BTC/USDT", 103.0)
    rec = w.reconcile()
    assert rec["ok"], rec
    w.on_research_close(r, 108.0, "take_profit")
    assert w.open_positions() == []
    closed = w.closed_positions()[0]
    proceeds = closed["qty"] * 108.0 * (1 - 0.0005)
    assert closed["pnl"] == pytest.approx(proceeds * (1 - 0.001) - closed["notional"] - closed["fee_entry"])
    assert w.cash() == pytest.approx(100.0 + closed["pnl"])
    assert w.reconcile()["ok"]
    assert [j["event"] for j in w.journal(5)][:2] == ["exit", "entry"]


def test_daily_loss_limit_blocks_new_entries_and_resets_next_day(w, monkeypatch):
    r = pos(entry=100.0, stop=95.0)
    w.offer(r)
    w.settle()
    w._day_start_equity()                                  # today's start = 100
    w.on_research_close(r, 1.0, "stop_loss")              # a huge loss: equity far below -5 %
    w.offer(pos(symbol="X/USDT", stop=90.0))
    d = w.settle()[0]
    assert d["decision"] == "rejected" and "daily loss limit" in d["reason"]
    monkeypatch.setattr(wallet, "_utc_day", lambda ts=None: "2999-01-01")   # next UTC day: new start equity
    w.offer(pos(symbol="Y/USDT", entry=10.0, stop=5.0))
    assert "daily loss limit" not in w.settle()[0]["reason"]


def test_daily_limit_cannot_be_raised_above_10_percent(w):
    w._set("settings", '{"daily_loss_limit_pct": 50}')
    assert w.settings()["daily_loss_limit_pct"] == 10.0


def test_strategy_auto_paused_after_20_losing_trades_and_unpause_is_manual(w, monkeypatch):
    monkeypatch.setitem(wallet.DEFAULTS, "max_open_positions", 1)
    monkeypatch.setitem(wallet.DEFAULTS, "duplicate_window_min", 0)
    monkeypatch.setitem(wallet.DEFAULTS, "daily_loss_limit_pct", 10.0)
    for i in range(20):
        w._set("day", "")                                 # keep the daily limit out of this test
        r = pos(symbol="L/USDT", entry=100.0, stop=90.0, strategy="loser")
        w.offer(r)
        assert w.settle()[0]["decision"] == "opened", i
        w.on_research_close(r, 99.0 if i % 4 else 101.0, "x")
    assert "loser" in w.paused()
    w.offer(pos(symbol="M/USDT", stop=90.0, strategy="loser"))
    assert "auto-paused" in w.settle()[0]["reason"]
    assert w.unpause("loser") and "loser" not in w.paused()


def test_wallet_api_is_mounted_and_read_only_get(w, monkeypatch):
    from fastapi.testclient import TestClient
    from sindhu_web import security, auth
    monkeypatch.setattr(security, "_is_lan_client", lambda h: True)
    monkeypatch.setattr(auth, "is_valid_session", lambda t: True)
    import cloud_runtime.app as cloud
    r = TestClient(cloud.app).get("/api/wallet")
    assert r.status_code == 200
    body = r.json()
    assert body["wallet"] == "MAIN_WALLET" and body["equity"] == 100.0 and body["reconciliation"]["ok"] and body["paper_only"] is True


def test_one_position_uses_at_most_a_quarter_of_equity_and_cash_never_goes_negative(w):
    w.offer(pos(entry=100.0, stop=99.0))                  # 1 % stop: risk-based size would be ~$100, capped at $25
    d = w.settle()[0]
    assert d["notional"] == pytest.approx(25.0)
    for i in range(3):
        w.offer(pos(symbol=f"Q{i}/USDT", entry=100.0, stop=99.0))
    w.settle()
    assert len(w.open_positions()) == 4 and w.cash() >= 0


def test_no_free_cash_is_said_plainly(w, monkeypatch):
    monkeypatch.setitem(wallet.DEFAULTS, "max_open_positions", 10)
    monkeypatch.setattr(wallet, "daily_limit_hit", lambda: (False, 100.0, 100.0))   # this test is about cash only
    w._set("cash", "0.00000000")
    w.offer(pos(stop=90.0))
    assert "no free cash" in w.settle()[0]["reason"]
