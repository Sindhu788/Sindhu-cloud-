"""Master Task 3, Phase 1.5/1.10/1.13/1.14: self_learning_engine/
discovery_cycle.py -- the full orchestration, with a fake run_batch_fn so
no real 50-coin backtest actually runs in a unit test.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from backtest_engine import strategy_library as lib
from data_engine import config as base_config, feature_toggles, storage
from self_learning_engine import discovery_cycle


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    # Real Governor.resource_ok() does a live psutil read -- deterministic
    # True keeps these tests from ever flaking under real CI/host load.
    patcher = patch("self_learning_engine.discovery_cycle.Governor.resource_ok", return_value=True)
    patcher.start()
    yield
    patcher.stop()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _seed_klines(exchange, symbol, start_ms, end_ms, step_ms=60_000 * 60):
    rows = []
    t = start_ms
    while t < end_ms:
        rows.append((exchange, symbol, t, 100.0, 101.0, 99.0, 100.5, 10.0, t + 59999, 1000.0, 5))
        t += step_ms
    with storage.get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO klines_1m
               (exchange, symbol, open_time, open, high, low, close, volume, close_time, quote_volume, trades)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )


def _seed_symbol(exchange, symbol):
    with storage.get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO symbols (exchange, symbol) VALUES (?, ?)", (exchange, symbol))


def _seed_paper_performance(name, concepts_used, pnl, is_win):
    cfg = StrategyConfig(
        name=name, timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="concept", name=concepts_used[0])],
        concepts_used=concepts_used,
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )
    strategy_id = lib.create(cfg)
    storage.update_paper_strategy_performance(strategy_id, name, pnl, is_win, None, _now())
    return strategy_id


def _fake_batch(exchange, batch_id, symbol_metrics):
    storage.create_batch(batch_id, "Test", exchange, {"initial_balance": 1000.0}, _now())
    for i, (total_trades, wins, profit_factor, risk_reward) in enumerate(symbol_metrics):
        storage.save_result(
            batch_id, f"SYM{i}USDT", "5m", "completed",
            {"total_trades": total_trades, "wins": wins, "losses": total_trades - wins,
             "final_balance": 1000.0, "profit_factor": profit_factor, "risk_reward": risk_reward},
            _now(),
        )
    return batch_id


def test_no_data_when_nothing_has_ever_been_scored(test_db):
    result = discovery_cycle.run_discovery_cycle(exchange="binance", symbols=["BTCUSDT"], force=True)
    assert result["status"] == "no_data"


def test_skips_when_weekly_cap_not_elapsed(test_db):
    storage.save_self_learning_cycle("prev", _now(), _now(), status="completed")
    result = discovery_cycle.run_discovery_cycle()
    assert result["status"] == "skipped_weekly_cap"


def test_skips_when_disabled_via_feature_toggle(test_db):
    feature_toggles.set_toggle("self_learning_engine_enabled", False)
    result = discovery_cycle.run_discovery_cycle()
    assert result["status"] == "skipped_weekly_cap"


def test_gate_reopens_after_7_days(test_db):
    old_started = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    storage.save_self_learning_cycle("prev", old_started, old_started, status="completed")
    result = discovery_cycle.run_discovery_cycle(exchange="binance", symbols=["BTCUSDT"])
    # Nothing scored yet -> no_data, but crucially NOT skipped_weekly_cap.
    assert result["status"] == "no_data"


def test_resource_limit_skips_the_cycle(test_db):
    with patch("self_learning_engine.discovery_cycle.Governor.resource_ok", return_value=False):
        result = discovery_cycle.run_discovery_cycle(force=True)
    assert result["status"] == "skipped_resource_limit"


def test_no_data_when_no_historical_candles_exist_yet(test_db):
    _seed_paper_performance("Combo Strategy", ["fvg", "order_block"], 100.0, True)
    result = discovery_cycle.run_discovery_cycle(exchange="binance", symbols=["BTCUSDT"], force=True)
    assert result["status"] == "no_data"


def test_full_cycle_accepts_a_candidate_that_clears_the_gate(test_db):
    _seed_paper_performance("Combo Strategy", ["fvg", "order_block"], 100.0, True)
    _seed_symbol("binance", "BTCUSDT")
    _seed_klines("binance", "BTCUSDT", 0, 60_000 * 60 * 24 * 30)

    good_metrics = [(30, 20, 1.8, 2.5)]  # 66.7% win, PF 1.8, well above any thin benchmark
    batches = iter(["disc1", "val1"])

    def fake_run_batch(config, exchange, symbols, settings, start_ms, end_ms):
        return _fake_batch(exchange, next(batches), good_metrics)

    result = discovery_cycle.run_discovery_cycle(
        exchange="binance", symbols=["BTCUSDT"], run_batch_fn=fake_run_batch, force=True,
    )
    assert result["status"] == "accepted"
    assert result["strategy_id"] is not None
    saved = lib.load(result["strategy_id"])
    assert saved.risk_reward >= 2.0

    attempts = storage.list_self_learning_attempts()
    assert attempts[0]["outcome"] == "accepted"


def test_full_cycle_rejects_a_candidate_that_fails_the_gate(test_db):
    _seed_paper_performance("Combo Strategy", ["fvg", "order_block"], 100.0, True)
    _seed_symbol("binance", "BTCUSDT")
    _seed_klines("binance", "BTCUSDT", 0, 60_000 * 60 * 24 * 30)

    bad_metrics = [(30, 10, 0.6, 1.5)]  # PF well below 1.0
    batches = iter(["disc1", "val1"])

    def fake_run_batch(config, exchange, symbols, settings, start_ms, end_ms):
        return _fake_batch(exchange, next(batches), bad_metrics)

    result = discovery_cycle.run_discovery_cycle(
        exchange="binance", symbols=["BTCUSDT"], run_batch_fn=fake_run_batch, force=True,
    )
    assert result["status"] == "rejected"
    assert result.get("strategy_id") is None

    attempts = storage.list_self_learning_attempts()
    assert attempts[0]["outcome"] == "rejected"


def test_structural_duplicate_is_rejected_before_any_backtest_runs(test_db):
    _seed_paper_performance("Combo Strategy", ["fvg", "order_block"], 100.0, True)
    _seed_symbol("binance", "BTCUSDT")
    _seed_klines("binance", "BTCUSDT", 0, 60_000 * 60 * 24 * 30)

    # Pre-create a strategy with the SAME concepts candidate_builder will
    # draw for combo ["breakout", "liquidity"] at variant 0 (fvg + the
    # structure fallback support/resistance) -- see candidate_builder.py.
    from self_learning_engine import candidate_builder
    probe_config, _, drawn = candidate_builder.build_candidate(["breakout", "liquidity"], variant=0)
    lib.create(StrategyConfig(
        name="Pre-existing near-identical", timeframes={"entry": "5m"},
        entry_conditions=probe_config.entry_conditions, concepts_used=probe_config.concepts_used,
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    ))

    mock_run_batch = MagicMock()
    result = discovery_cycle.run_discovery_cycle(
        exchange="binance", symbols=["BTCUSDT"], run_batch_fn=mock_run_batch, force=True,
    )
    assert result["status"] == "rejected"
    assert "duplicate" in result["narrative"]
    mock_run_batch.assert_not_called()
