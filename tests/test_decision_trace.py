from datetime import datetime, timezone

from data_engine import db_size_guard, storage
from paper_trading import decision_trace as dt


def _d(decision, reason, symbol="BTC/USDT", strategy="Ichimoku 15m", age_ms=120000):
    return {"exchange": "okx", "symbol": symbol, "direction": "long", "decision": decision, "reason": reason, "strategy_id": "s1",
            "strategy_name": strategy, "timeframe": "15m", "created_at": datetime.now(timezone.utc).isoformat(),
            "market_snapshot": {"candle_receipt": {"age_ms": age_ms}}}


def test_classification_of_known_reasons():
    assert dt.classify("no_trade", "Stale closed market candles rejected.") == "market_data"
    assert dt.classify("no_trade", "No entry rule matched.") == "entry_rule"
    assert dt.classify("rejected", "max coins for this strategy reached (5)") == "max_coins"
    assert dt.classify("rejected", "strategy paused (Drawdown Protection): 7 consecutive losses") == "drawdown_breaker"
    assert dt.classify("rejected", "KILL SWITCH ACTIVE -- all trading halted") == "kill_switch"
    assert dt.classify("rejected", "position lock: identical position already open") == "position_lock"
    assert dt.classify("rejected", "opposite long position already open (policy=block)") == "opposite_signal"
    assert dt.classify("rejected", "no stop-loss could be computed -- risk cannot be sized") == "sizing"
    assert dt.classify("opened", "") is None


def test_gate_results_are_ordered_pass_then_fail_then_not_reached():
    res = {g["gate"]: g["result"] for g in dt.gate_results("rejected", "max_coins")}
    assert res["market_data"] == "pass" and res["entry_rule"] == "pass" and res["max_coins"] == "fail" and res["sizing"] == "not_reached"
    assert all(g["result"] == "pass" for g in dt.gate_results("opened", None))


def test_record_query_and_summary_answer_why(test_db):
    assert dt.record([_d("rejected", "max coins for this strategy reached (5)"), _d("opened", "ok", symbol="ETH/USDT"),
                      _d("no_trade", "Stale closed market candles rejected.", symbol="SOL/USDT")]) == 3
    r = dt.query(coin="btc")
    assert len(r["decisions"]) == 1 and r["decisions"][0]["failed_gate"] == "max_coins" and r["decisions"][0]["data_age_s"] == 120.0
    assert dt.query(coin="BTCUSDT")["decisions"][0]["coin"] == "okx:BTC/USDT"
    assert dt.query(outcome="opened")["decisions"][0]["coin"].endswith("ETH/USDT")
    s = dt.summary()
    assert s["by_outcome"]["opened"] == 1 and s["by_gate"]["market_data"] == 1


def test_query_before_any_scan_is_empty_not_an_error(test_db):
    assert dt.query(coin="BTC")["decisions"] == []


def test_trace_table_is_pruned_with_the_other_diagnostics(test_db):
    dt.record([_d("opened", "ok")])
    assert "paper_decision_trace" in db_size_guard._PRUNABLE
    deleted = db_size_guard.prune_append_only_logs(now=datetime(2027, 1, 1, tzinfo=timezone.utc))
    assert deleted.get("paper_decision_trace") == 1


def test_engine_flushes_decisions_in_small_batches_and_writes_the_trace():
    import inspect
    from paper_trading import engine
    src = inspect.getsource(engine)
    assert "len(self._pending_decisions) >= 10" in src and "decision_trace.record(pending)" in src
