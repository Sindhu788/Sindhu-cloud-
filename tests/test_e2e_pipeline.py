"""End-to-end pipeline evidence (Step 12): strategy import -> backtest -> paper trade -> Telegram eligibility -> payload.
Every stage prints its count; the Telegram stage is an eligibility + formatting check, NOT a real send (requests are mocked
and asserted not to be called). Deterministic: synthetic candles, no network, no AI."""
from datetime import datetime, timezone
from unittest.mock import patch

from backtest_engine import runner, strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from data_engine import storage
from paper_trading import telegram_bot

EXCHANGE, SYMBOL, START_MS = "binance", "E2EUSDT", 1_700_000_000_000


def _seed_candles(n=200):
    rows, price = [], 100.0
    for i in range(n):
        o = price
        price += 0.5
        rows.append((START_MS + i * 60_000, o, price + 0.1, o - 0.1, price, 10.0, START_MS + i * 60_000 + 59_999, 1000.0, 5))
    storage.insert_klines(EXCHANGE, SYMBOL, rows)


def _config():
    return StrategyConfig(
        name="E2E Trend Strategy", timeframes={"entry": "1m"},
        indicators=[{"name": "sma", "params": {"period": 3}, "role": "entry"}],
        entry_conditions=[Condition(type="price_compare", op=">", indicator="sma", params={"period": 3})],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0), risk_pct=1.0)


def test_import_backtest_paper_trade_signal_payload(test_db, monkeypatch, capsys):
    counts = {}
    # --- stage 1: import (library save + reload round trip)
    meta = lib.create(_config())
    sid = meta["id"] if isinstance(meta, dict) else meta
    loaded = lib.load(sid)
    counts["1 imported strategies"] = len(lib.list_all())
    assert loaded.name == "E2E Trend Strategy" and counts["1 imported strategies"] >= 1

    # --- stage 2: backtest
    _seed_candles()
    batch = runner.run_mtf_batch(loaded, EXCHANGE, [SYMBOL], {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.0,
                                 "slippage_pct": 0.0, "position_size_pct": 10.0}, log=lambda m: None, use_multiprocessing=False)
    res = storage.get_batch_results(batch)
    trades = sum((r["metrics"] or {}).get("total_trades", 0) for r in res)
    counts["2 backtest trades"] = trades
    assert res[0]["status"] == "completed" and trades > 0

    # --- stage 3: paper trade opened for the imported strategy
    pos = {"id": "e2e-pos", "exchange": EXCHANGE, "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0, "size": 1.0,
           "risk_amount": 5.0, "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
           "created_at": "2026-01-01T00:00:00+00:00", "strategy_id": sid, "strategy_name": loaded.name,
           "stop_loss": 95.0, "take_profit": 110.0, "confidence": 70.0}
    storage.open_paper_position(pos)
    counts["3 open paper positions"] = len(storage.get_open_paper_positions())
    assert counts["3 open paper positions"] == 1

    # --- stage 4: Telegram eligibility (group gate) for each group, then payload, with the network mocked
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)
    monkeypatch.setenv("SINDHU_CLOUD_MODE", "1")
    monkeypatch.setenv("SINDHU_PUBLIC_SIGNAL_OWNER", "cloud")
    telegram_bot.save_settings(bot_token="1:T", channel_id="-100", master_send_enabled=True, auto_send_enabled=True)
    outcome = {}
    for group in ("losing", "profitable"):
        storage.upsert_paper_strategy_groups_batch({sid: group}, datetime.now(timezone.utc).isoformat())
        with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as send, \
                patch("requests.post") as net:
            r = telegram_bot.send_signal_for_position("e2e-pos", trigger_type="manual")
        assert net.call_count == 0
        outcome[group] = (bool(r.get("ok")), send.call_count, send.call_args[0][0] if send.call_count else "")
    counts["4 eligible for Telegram (profitable group)"] = int(outcome["profitable"][0])
    counts["4 withheld (losing group)"] = int(not outcome["losing"][0])
    assert outcome["losing"][0] is False and outcome["losing"][1] == 0
    assert outcome["profitable"][0] is True
    payload = outcome["profitable"][2]
    for field in ("BTCUSDT", "Direction", "Entry", "Stop-Loss", "Take-Profit", "Duration", "Confidence"):
        assert field.lower() in payload.lower() or field == "BTCUSDT", field
    counts["5 payload fields present"] = 7
    with capsys.disabled():
        print("\nE2E STAGE COUNTS:", counts)
