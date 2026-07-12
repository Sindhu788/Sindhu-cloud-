"""Regression safety net for the bugs found and fixed in this project's
backtesting pipeline this session:

1. The bar-simulation freeze (progress-queue blocking worker processes).
2. The Knowledge Engine "lesson veto" bug (a Lesson silently blocking a
   Strategy's own valid trade signal).
3. The Backtest History API/page.
4. The one-backtest-at-a-time enforcement.

Every test uses synthetic, deterministic OHLCV data (strictly increasing
close prices) seeded into an isolated temp database (see conftest.py), not
real market data -- these tests check application BEHAVIOR (does it hang,
does a Lesson block a trade it shouldn't, does the API return sane data,
is a second concurrent batch rejected), not trading/strategy correctness.
"""

import pytest
from fastapi import HTTPException

from data_engine import storage
from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import runner
from backtest_engine.reports import quick_batch_summary
from backtest_engine.engine import run_backtest as engine_run_backtest
from backtest_engine.configured_strategy import ConfiguredStrategy
from backtest_engine.mtf_context import MultiTimeframeContext
from sindhu_web.jobs import job_manager
from sindhu_web.api.backtesting import RunRequest, run_backtest as api_run_backtest

EXCHANGE = "binance"
SYMBOL = "TESTUSDT"
START_MS = 1_700_000_000_000  # arbitrary fixed epoch -- deterministic, no real-time dependency


def _seed_synthetic_candles(n=60, start_price=100.0):
    """n one-minute candles with a strictly increasing close price --
    guarantees close > sma(3) on every bar past warmup, so a simple
    strategy reliably produces entry signals without depending on any
    real market data or specific ICT/SMC concept detection."""
    rows = []
    price = start_price
    for i in range(n):
        open_time = START_MS + i * 60_000
        close_time = open_time + 59_999
        o = price
        price += 0.5
        c = price
        h = c + 0.1
        l = o - 0.1
        rows.append((open_time, o, h, l, c, 10.0, close_time, 1000.0, 5))
    storage.insert_klines(EXCHANGE, SYMBOL, rows)


def _simple_strategy_config(name="TestStrategy"):
    return StrategyConfig(
        name=name,
        timeframes={"entry": "1m"},
        indicators=[{"name": "sma", "params": {"period": 3}, "role": "entry"}],
        entry_conditions=[
            Condition(type="price_compare", op=">", indicator="sma", params={"period": 3}),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )


def _settings():
    return {
        "initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.0,
        "slippage_pct": 0.0, "position_size_pct": 10.0,
    }


def test_backtest_completes_without_hanging(test_db):
    """A full backtest batch must reach 'completed' status. Runs
    sequentially (use_multiprocessing=False) so a hang shows up as this
    test itself hanging/timing out rather than a background process
    silently stuck -- pytest-timeout isn't required since the dataset is
    tiny (60 bars), so this either finishes in well under a second or
    the freeze bug has regressed."""
    _seed_synthetic_candles()
    cfg = _simple_strategy_config()
    batch_id = runner.run_mtf_batch(
        cfg, EXCHANGE, [SYMBOL], _settings(),
        log=lambda msg: None, use_multiprocessing=False,
    )
    batch = storage.get_batch(batch_id)
    assert batch["status"] == "completed"

    results = storage.get_batch_results(batch_id)
    assert len(results) == 1
    assert results[0]["status"] == "completed"


def test_lesson_does_not_block_valid_trade(test_db):
    """Regression test for the lesson-veto bug: a Lesson (here, a stub
    KnowledgeEngine that unconditionally rejects every check) must NEVER
    prevent a Strategy's own validated signal from becoming a real trade.
    Before the fix, engine.py nulled the signal whenever check() returned
    approved=False; this test fails immediately if that regresses."""
    _seed_synthetic_candles()
    cfg = _simple_strategy_config()
    strat = ConfiguredStrategy(cfg)
    ctx = MultiTimeframeContext(EXCHANGE, SYMBOL, cfg.timeframes, None, None)
    merged = strat.prepare_context(ctx)

    class AlwaysBlockKnowledgeEngine:
        def check(self, df, i, direction):
            return False, "blocked by test lesson"

    trades, equity_curve, final_balance = engine_run_backtest(
        merged, strat, _settings(), knowledge_engine=AlwaysBlockKnowledgeEngine(),
    )
    assert len(trades) > 0, "a Lesson must never block a Strategy's own valid signal"


def test_backtest_history_returns_valid_data(test_db):
    """quick_batch_summary() backs the /api/backtest-history endpoint --
    verify it returns sane, complete data for a real completed batch."""
    _seed_synthetic_candles()
    cfg = _simple_strategy_config()
    batch_id = runner.run_mtf_batch(
        cfg, EXCHANGE, [SYMBOL], _settings(),
        log=lambda msg: None, use_multiprocessing=False,
    )
    summary = quick_batch_summary(batch_id)
    assert summary is not None
    assert summary["batch_id"] == batch_id
    assert summary["strategy"] == "TestStrategy"
    assert summary["symbol_count"] == 1
    assert summary["combos_completed"] == 1
    assert isinstance(summary["total_trades"], int)
    assert isinstance(summary["win_rate"], float)
    assert summary["total_pnl"] is not None


def test_second_concurrent_backtest_is_rejected(test_db):
    """Regression test for one-backtest-at-a-time: calling the real
    /api/backtesting/run endpoint function while another backtest job is
    already 'running' must raise HTTPException(409), not silently start
    a second batch in parallel."""
    job_id = "test-already-running-job"
    fake_job = job_manager.Job(job_id, "backtest")
    fake_job.status = "running"
    fake_job.progress = {"done": 0, "total": 1, "current_strategy": "SomeOtherStrategy"}
    with job_manager._lock:
        job_manager._jobs[job_id] = fake_job

    try:
        _seed_synthetic_candles()
        cfg = _simple_strategy_config(name="SecondStrategy")
        req = RunRequest(config=cfg.to_dict(), all_coins=False, symbols=[SYMBOL])
        with pytest.raises(HTTPException) as exc_info:
            api_run_backtest(req)
        assert exc_info.value.status_code == 409
        assert "already running" in str(exc_info.value.detail)
    finally:
        with job_manager._lock:
            job_manager._jobs.pop(job_id, None)
