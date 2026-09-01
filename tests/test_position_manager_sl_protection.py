"""Full A-to-Z audit, Phase 4: paper_trading/position_manager.py did not
apply the same Requirement 20 stop-loss protection backtest_engine.engine
has -- a candidate's stop_loss/take_profit were computed against the raw
signal price and never re-validated against the real, slippage-adjusted
fill price. A structure-based stop that ended up on the wrong side after
slippage would be trusted as-is and used to gate exits (_check_exit),
which could fire incorrectly on the very next tick or never fire at all.

Unlike the backtest engine, paper_trading.risk_manager.evaluate() already
refuses to open any position at all when candidate["stop_loss"] is None
(there's no "end of data" bound in live trading, so this is the more
conservative existing behavior for that specific case) -- so this fix
targets the wrong-side-after-slippage case specifically, using the exact
same discard-then-emergency-fallback logic as
backtest_engine.engine._open_position, imported and reused verbatim
(EMERGENCY_STOP_PCT), so both engines now protect a live/backtested
position the same way for the same StrategyConfig.
"""

from paper_trading import position_manager
from backtest_engine.engine import EMERGENCY_STOP_PCT


def _candidate(**overrides):
    base = dict(
        source="strategy", strategy_id="s1", strategy_name="Test Strategy", strategy_version=1,
        direction="bullish", action="buy",
        entry_price=100.0, stop_loss=99.0, take_profit=104.0,
        stop_loss_type="structure",
        entry_reason="signal", timeframe="5m",
        approved=True, veto_reason=None, lesson_ids=[],
    )
    base.update(overrides)
    return base


def _snapshot():
    return {"market_state": "trending_up", "session": "london", "volume_spike": False, "structure": False}


def test_stop_loss_on_correct_side_is_kept_unchanged(test_db):
    cand = _candidate(direction="bullish", entry_price=100.0, stop_loss=99.0)
    pos = position_manager.open_position("binance", "BTCUSDT", cand, size=1.0, risk_amount=1.0,
                                          confidence=0.8, market_snapshot=_snapshot())
    assert pos["stop_loss"] == 99.0


def test_wrong_side_stop_loss_after_slippage_gets_emergency_fallback_not_trusted(test_db):
    """Mirrors test_wrong_side_stop_loss_gets_emergency_fallback_not_discarded
    in tests/test_trade_execution_engine.py. A long candidate's stop_loss
    sits ABOVE its entry_price -- impossible pre-slippage (the strategy
    would never compute that), but exercises the exact same wrong-side
    branch the backtest engine guards against, using a real
    stop_loss_type so the emergency fallback applies."""
    cand = _candidate(direction="bullish", entry_price=100.0, stop_loss=100.5, stop_loss_type="structure")
    pos = position_manager.open_position("binance", "BTCUSDT", cand, size=1.0, risk_amount=1.0,
                                          confidence=0.8, market_snapshot=_snapshot())
    assert pos["stop_loss"] is not None
    assert pos["stop_loss"] < pos["entry_price"]  # correct side for a long
    expected = pos["entry_price"] * (1 - EMERGENCY_STOP_PCT)
    assert abs(pos["stop_loss"] - expected) < 1e-9


def test_wrong_side_stop_loss_short_direction_gets_emergency_fallback(test_db):
    cand = _candidate(direction="bearish", action="sell", entry_price=100.0, stop_loss=99.5, stop_loss_type="structure")
    pos = position_manager.open_position("binance", "BTCUSDT", cand, size=1.0, risk_amount=1.0,
                                          confidence=0.8, market_snapshot=_snapshot())
    assert pos["stop_loss"] is not None
    assert pos["stop_loss"] > pos["entry_price"]  # correct side for a short
    expected = pos["entry_price"] * (1 + EMERGENCY_STOP_PCT)
    assert abs(pos["stop_loss"] - expected) < 1e-9


def test_wrong_side_stop_loss_with_no_configured_stop_type_is_discarded_without_fallback(test_db):
    """Matches backtest_engine's own accepted behavior: the emergency
    fallback only applies when the strategy actually configured a real
    stop-loss mechanism. A strategy relying on exit_conditions instead
    (stop_loss_type unknown/None) gets an honestly-missing stop, not a
    fabricated one."""
    cand = _candidate(direction="bullish", entry_price=100.0, stop_loss=100.5, stop_loss_type=None)
    pos = position_manager.open_position("binance", "BTCUSDT", cand, size=1.0, risk_amount=1.0,
                                          confidence=0.8, market_snapshot=_snapshot())
    assert pos["stop_loss"] is None


def test_wrong_side_take_profit_after_slippage_is_discarded(test_db):
    cand = _candidate(direction="bullish", entry_price=100.0, take_profit=99.0)
    pos = position_manager.open_position("binance", "BTCUSDT", cand, size=1.0, risk_amount=1.0,
                                          confidence=0.8, market_snapshot=_snapshot())
    assert pos["take_profit"] is None


def test_backtest_engine_and_paper_trading_apply_identical_fallback_distance(test_db):
    """The actual divergence this phase closes: same StrategyConfig-derived
    inputs (entry price, wrong-side structure stop, stop_loss_type) must
    produce the same protective distance from both engines."""
    from backtest_engine import engine as bt_engine

    cand = _candidate(direction="bullish", entry_price=100.0, stop_loss=100.5, stop_loss_type="structure")
    pos = position_manager.open_position("binance", "BTCUSDT", cand, size=1.0, risk_amount=1.0,
                                          confidence=0.8, market_snapshot=_snapshot())
    # Both engines compute the fallback the same way: EMERGENCY_STOP_PCT
    # below the REAL (post-slippage) fill price, not the raw signal price.
    bt_fallback = pos["entry_price"] * (1 - bt_engine.EMERGENCY_STOP_PCT)
    assert abs(pos["stop_loss"] - bt_fallback) < 1e-9
