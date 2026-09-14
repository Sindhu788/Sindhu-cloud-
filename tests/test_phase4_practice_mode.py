"""Grand Master Batch, Phase 4 Item 3 -- Practice Mode.

Reuses the exact real confidence-scoring and position-sizing logic
every real trade goes through, fed a CEO-typed hypothetical instead of
a real generated signal. Never opens a position.
"""

import pytest

from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from backtest_engine import strategy_library as lib
from data_engine import storage
from paper_trading import config as pt_config, practice_mode


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path))
    yield


def _config(name):
    cfg = StrategyConfig(
        name=name, timeframes={"entry": "1h"},
        indicators=[{"name": "sma", "params": {"period": 3}, "role": "entry"}],
        entry_conditions=[Condition(type="price_compare", op=">", indicator="sma", params={"period": 3})],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    return cfg


def test_unknown_strategy_raises(test_db):
    with pytest.raises(ValueError):
        practice_mode.evaluate("does-not-exist", "BTCUSDT", "bullish", 100.0, 95.0)


def test_evaluate_returns_confidence_and_sizing_never_opens_a_position(test_db, tmp_path, monkeypatch):
    from data_engine import config as base_config
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    sid = lib.create(_config("Test Strategy"))

    result = practice_mode.evaluate(sid, "BTCUSDT", "bullish", 100.0, 95.0, take_profit=110.0)

    assert result["practice_only"] is True
    assert result["strategy_id"] == sid
    assert result["strategy_name"] == "Test Strategy"
    assert 0 <= result["confidence"] <= 100
    assert result["sizing"]["size"] > 0
    assert result["sizing"]["risk_amount"] is not None
    # Real proof nothing was opened: no open paper positions exist anywhere.
    assert storage.get_open_paper_positions() == []


def test_trending_market_aligned_with_direction_raises_confidence(test_db, tmp_path, monkeypatch):
    from data_engine import config as base_config
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    sid = lib.create(_config("Test Strategy"))

    ranging = practice_mode.evaluate(sid, "BTCUSDT", "bullish", 100.0, 95.0, market_state="ranging")
    trending = practice_mode.evaluate(sid, "BTCUSDT", "bullish", 100.0, 95.0, market_state="trending_up")
    assert trending["confidence"] > ranging["confidence"]


def test_sizing_uses_real_configured_balance_and_risk(test_db, tmp_path, monkeypatch):
    from data_engine import config as base_config
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    sid = lib.create(_config("Test Strategy"))
    pt_config.update(initial_balance=5000.0, risk_pct_default=2.0)

    result = practice_mode.evaluate(sid, "BTCUSDT", "bullish", 100.0, 95.0)
    assert result["balance_used"] == 5000.0
    assert result["risk_pct_used"] == 2.0
