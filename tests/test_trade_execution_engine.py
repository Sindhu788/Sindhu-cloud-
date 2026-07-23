"""Phase 1 (BACKTESTING_MASTER_SPEC.md Requirement 10/11/17): the Trade
Execution Engine, PnL Engine, and Risk Engine additions -- Market, Limit,
Stop, Signal Candle High/Low, Next Candle Open, Current Candle Close entry
types; Partial Take Profit, Break Even, Trailing Stop, Time Exit; spread,
leverage, daily loss limit, max drawdown limit; and no-double-counting PnL
bookkeeping.

Every test builds a tiny, fully deterministic synthetic candle sequence
and a minimal test-only Strategy that fires an exact, known signal at an
exact, known bar -- so each execution mechanism can be checked against a
hand-computed expected fill price/bar, not just "did trades happen".
"""

import pandas as pd
import pytest

from backtest_engine.engine import run_backtest, _position_size
from backtest_engine.strategy_config import StrategyConfig
from strategies.base import Strategy, Signal


def _make_df(rows):
    """rows: list of (open, high, low, close) tuples, one bar apart."""
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame({
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
        "volume": [100.0] * len(rows),
    }, index=idx)


class _FixedSignalStrategy(Strategy):
    """Fires exactly one entry signal at `fire_at_bar`, everything else is
    left None/default so a test only exercises the execution mechanic
    under study, not condition-evaluation logic (tested elsewhere)."""

    def __init__(self, fire_at_bar, action="buy", stop_loss=None, take_profit=None, config=None):
        self.fire_at_bar = fire_at_bar
        self.action = action
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.config = config
        self._fired = False

    def prepare(self, df):
        return df

    def on_bar(self, df, i, position):
        if position is None and not self._fired and i == self.fire_at_bar:
            self._fired = True
            return Signal(action=self.action, stop_loss=self.stop_loss, take_profit=self.take_profit, reason="test signal")
        return None


class _RepeatingSignalStrategy(Strategy):
    """Fires a fresh entry signal on every bar it's flat -- used to test
    circuit breakers (daily loss limit / max drawdown limit) that need
    several trades to accumulate losses."""

    def __init__(self, action="buy", stop_loss_offset=1.0, config=None):
        self.action = action
        self.stop_loss_offset = stop_loss_offset
        self.config = config

    def prepare(self, df):
        return df

    def on_bar(self, df, i, position):
        if position is None:
            price = df["close"].iloc[i]
            sl = price - self.stop_loss_offset if self.action == "buy" else price + self.stop_loss_offset
            return Signal(action=self.action, stop_loss=sl, take_profit=None, reason="repeat signal")
        return None


def _settings(**overrides):
    base = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.0,
            "slippage_pct": 0.0, "position_size_pct": 10.0}
    base.update(overrides)
    return base


# ------------------------------------------------------------ entry types

def test_market_entry_fills_at_signal_bar_close():
    df = _make_df([(100, 101, 99, 100), (100, 105, 95, 102), (102, 103, 101, 103)])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy")
    trades, equity, bal = run_backtest(df, strat, _settings())
    assert len(trades) == 1
    assert trades[0]["entry_price"] == pytest.approx(102.0)
    assert trades[0]["entry_type"] == "market"


def test_current_candle_close_is_identical_to_market():
    """Requirement 10: "market" and "current_candle_close" both fill at
    the signal bar's close -- a bar-based backtest has no way to tell them
    apart, so they must produce byte-identical results, not one silently
    ignored in favor of the other."""
    rows = [(100, 101, 99, 100), (100, 105, 95, 102), (102, 103, 101, 103)]
    df1, df2 = _make_df(rows), _make_df(rows)
    cfg = StrategyConfig(name="t", entry_type="current_candle_close")
    strat_market = _FixedSignalStrategy(fire_at_bar=1, action="buy")
    strat_ccc = _FixedSignalStrategy(fire_at_bar=1, action="buy", config=cfg)
    t1, _, b1 = run_backtest(df1, strat_market, _settings())
    t2, _, b2 = run_backtest(df2, strat_ccc, _settings())
    assert t1[0]["entry_price"] == t2[0]["entry_price"]
    assert b1 == b2
    assert t2[0]["entry_type"] == "current_candle_close"


def test_limit_entry_waits_for_pullback_and_fills_at_trigger_price():
    cfg = StrategyConfig(name="t", entry_type="limit", entry_price_offset_pct=1.0)
    df = _make_df([
        (100, 101, 99, 100),        # bar 0
        (100, 102, 99.5, 101),      # bar 1: signal fires, close=101 -> trigger = 101*0.99 = 99.99
        (101, 101.5, 99.0, 100.5),  # bar 2: low=99.0 <= 99.99 -> fills here
        (100.5, 105, 100, 104),     # bar 3
    ])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy", config=cfg)
    trades, equity, bal = run_backtest(df, strat, _settings())
    assert len(trades) == 1
    assert trades[0]["entry_price"] == pytest.approx(99.99, abs=1e-9)
    assert trades[0]["entry_type"] == "limit"


def test_limit_entry_never_fills_if_price_never_returns():
    cfg = StrategyConfig(name="t", entry_type="limit", entry_price_offset_pct=5.0)
    df = _make_df([
        (100, 101, 99, 100),
        (100, 102, 99.5, 101),   # signal fires, trigger = 101*0.95 = 95.95, never reached below
        (101, 108, 100, 107),
        (107, 110, 106, 109),
    ])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy", config=cfg)
    trades, equity, bal = run_backtest(df, strat, _settings())
    assert len(trades) == 0


def test_stop_entry_waits_for_breakout_and_fills_at_trigger_price():
    cfg = StrategyConfig(name="t", entry_type="stop", entry_price_offset_pct=1.0)
    df = _make_df([
        (100, 101, 99, 100),
        (100, 102, 99.5, 101),      # signal fires, close=101 -> trigger = 101*1.01 = 102.01
        (101, 101.8, 100, 101.5),   # high=101.8 < 102.01, no fill yet
        (101.5, 103, 101, 102.5),   # high=103 >= 102.01 -> fills here
    ])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy", config=cfg)
    trades, equity, bal = run_backtest(df, strat, _settings())
    assert len(trades) == 1
    assert trades[0]["entry_price"] == pytest.approx(102.01, abs=1e-9)
    assert trades[0]["entry_type"] == "stop"


def test_signal_candle_high_entry_fills_at_signal_bars_own_high():
    cfg = StrategyConfig(name="t", entry_type="signal_candle_high")
    df = _make_df([
        (100, 101, 99, 100),
        (100, 105, 99, 102),     # signal fires here; signal bar's own HIGH = 105
        (102, 104, 101, 103),    # high=104 < 105, no fill
        (103, 106, 102, 105),    # high=106 >= 105 -> fills at exactly 105
    ])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy", config=cfg)
    trades, equity, bal = run_backtest(df, strat, _settings())
    assert len(trades) == 1
    assert trades[0]["entry_price"] == pytest.approx(105.0)
    assert trades[0]["entry_type"] == "signal_candle_high"


def test_signal_candle_low_entry_fills_at_signal_bars_own_low():
    cfg = StrategyConfig(name="t", entry_type="signal_candle_low")
    df = _make_df([
        (100, 101, 99, 100),
        (100, 102, 95, 99),      # signal fires (sell); signal bar's own LOW = 95
        (99, 100, 96, 97),       # low=96 > 95, no fill
        (97, 98, 94, 95),        # low=94 <= 95 -> fills at exactly 95
    ])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="sell", config=cfg)
    trades, equity, bal = run_backtest(df, strat, _settings())
    assert len(trades) == 1
    assert trades[0]["entry_price"] == pytest.approx(95.0)
    assert trades[0]["entry_type"] == "signal_candle_low"
    assert trades[0]["side"] == "short"


def test_next_candle_open_fills_at_the_immediately_following_bars_open():
    cfg = StrategyConfig(name="t", entry_type="next_candle_open")
    df = _make_df([
        (100, 101, 99, 100),
        (100, 105, 95, 102),     # signal fires here
        (103.5, 106, 103, 105),  # next bar -- fills at THIS bar's open (103.5), not close
        (105, 108, 104, 107),
    ])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy", config=cfg)
    trades, equity, bal = run_backtest(df, strat, _settings())
    assert len(trades) == 1
    assert trades[0]["entry_price"] == pytest.approx(103.5)
    assert trades[0]["entry_type"] == "next_candle_open"


def test_pending_order_never_fills_on_its_own_signal_bar():
    """No-look-ahead guard: a stop/limit trigger derived from bar i's own
    close must never be checked against bar i's own high/low -- only bars
    AFTER it. Craft a case where bar i's OWN high would satisfy the
    trigger if (incorrectly) checked same-bar."""
    cfg = StrategyConfig(name="t", entry_type="stop", entry_price_offset_pct=0.5)
    df = _make_df([
        (100, 101, 99, 100),
        (100, 110, 99.5, 100),   # signal fires here; close=100 -> trigger=100.5;
                                 # this SAME bar's high (110) already exceeds it --
                                 # must NOT fill on this bar.
        (100, 100.3, 99, 100),   # high=100.3 < 100.5, still no fill
        (100, 101, 100, 100.6),  # high=101 >= 100.5 -> fills here
    ])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy", config=cfg)
    trades, equity, bal = run_backtest(df, strat, _settings())
    assert len(trades) == 1
    assert trades[0]["entry_time"] > df.index[1].value // 1_000_000


def test_wrong_side_take_profit_from_slippage_is_discarded_not_trusted():
    """Final Audit regression test: a strategy hands the engine a
    take_profit that's on the CORRECT side of the raw signal price, but
    slippage alone pushes the real fill_price past it -- found live via
    the Phase 2 Verification Engine (Liquidity Sweeps, PDH-PDL Signal
    Candle Strategy both had real trades exactly like this). Must be
    discarded (None), never kept and silently mislabeled."""
    df = _make_df([
        (100, 101, 99, 100),
        (100, 105, 95, 100),   # signal fires: buy, tp=100.03 -- valid vs raw price 100,
                                # but 1% slippage pushes the real fill to 101 > tp.
        (100, 106, 99, 104),
    ])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy", stop_loss=90.0, take_profit=100.03)
    trades, equity, bal = run_backtest(df, strat, _settings(slippage_pct=1.0))
    assert len(trades) == 1
    assert trades[0]["entry_price"] == pytest.approx(101.0)  # 100 * 1.01
    assert trades[0]["take_profit"] is None  # discarded, not silently wrong-side
    assert trades[0]["stop_loss"] == pytest.approx(90.0)  # still valid, untouched


def test_wrong_side_stop_loss_is_discarded_not_trusted():
    """The guard in _open_position() is a GENERAL safety net, not specific
    to slippage-caused invalidation -- entry-side slippage structurally
    can only ever push a fill TOWARD the take_profit side and AWAY from
    the stop_loss side (a "worse" fill is, by definition, less profitable,
    i.e. closer to a smaller-profit take-profit level), so a wrong-side
    stop_loss in practice comes from elsewhere (e.g. a stale/buggy
    structural-zone computation, same bug class as the original eb1ca8f
    fix). Constructed directly here to prove the guard catches it
    regardless of WHY it's wrong, not just the one mechanism that happens
    to be easy to reproduce with slippage."""
    df = _make_df([
        (100, 101, 99, 100),
        (100, 101, 95, 100),   # signal fires: buy at ~100, but sl is ABOVE entry --
                                # already wrong-side even before any slippage.
        (100, 106, 94, 96),
    ])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy", stop_loss=100.5, take_profit=110.0)
    trades, equity, bal = run_backtest(df, strat, _settings())
    assert len(trades) == 1
    assert trades[0]["stop_loss"] is None  # discarded, not silently wrong-side
    assert trades[0]["take_profit"] == pytest.approx(110.0)  # still valid, untouched


# ------------------------------------------------------------ exit types

def test_partial_take_profit_splits_size_without_double_counting():
    cfg = StrategyConfig(name="t", partial_take_profit={"trigger_rr": 1.0, "close_fraction": 0.5})
    df = _make_df([
        (100, 101, 99, 100),
        (100, 101, 99, 100),      # signal fires: buy, sl=95 (risk=5), no tp -> 1R = 105
        (100, 106, 99, 104),      # high=106 >= 105 -> partial fires here, 50% closed @105
        (104, 104, 90, 92),       # low=90 <= sl(95) -> remainder stopped out @95
    ])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy", stop_loss=95.0, take_profit=None)
    strat.config = cfg
    trades, equity, bal = run_backtest(df, strat, _settings())
    assert len(trades) == 2
    partial, final = trades[0], trades[1]
    assert partial["is_partial"] is True
    assert partial["exit_reason"] == "partial_take_profit"
    assert partial["exit_price"] == pytest.approx(105.0)
    assert final["is_partial"] is False
    assert final["exit_reason"] == "stop_loss"
    # Sizes must sum back to exactly the original position size -- nothing
    # lost, nothing duplicated.
    assert partial["size"] + final["size"] == pytest.approx(partial["size"] / 0.5)
    # Balance change must equal the sum of both trades' net pnl exactly.
    assert bal == pytest.approx(1000.0 + partial["pnl"] + final["pnl"])


def test_partial_take_profit_never_fires_twice():
    cfg = StrategyConfig(name="t", partial_take_profit={"trigger_rr": 1.0, "close_fraction": 0.5})
    df = _make_df([
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 110, 99, 108),    # partial fires once here (>= 105)
        (108, 115, 107, 112),   # still above 105 -- must NOT fire a second partial
        (112, 112, 98, 100),    # eventually stops out
    ])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy", stop_loss=95.0, take_profit=None)
    strat.config = cfg
    trades, equity, bal = run_backtest(df, strat, _settings())
    partials = [t for t in trades if t["is_partial"]]
    assert len(partials) == 1


def test_break_even_moves_stop_to_entry_and_prevents_a_loss():
    cfg = StrategyConfig(name="t", breakeven_at_rr=1.0)

    # ConfiguredStrategy already implements breakeven via manage_position();
    # here we exercise it directly through a lightweight strategy that
    # mimics the same manage_position contract instead of pulling in the
    # full condition-parsing machinery.
    class _BreakevenStrategy(_FixedSignalStrategy):
        def manage_position(self, df, i, position):
            price = df["close"].iloc[i]
            if "_original_stop" not in position:
                position["_original_stop"] = position["stop_loss"]
            risk = abs(position["entry_price"] - position["_original_stop"])
            if position["side"] == "long" and (price - position["entry_price"]) >= risk:
                position["stop_loss"] = position["entry_price"]

    df = _make_df([
        (100, 101, 99, 100),
        (100, 101, 99, 100),     # signal fires: buy, sl=95 (risk=5)
        (100, 106, 99, 105),     # close=105 -> unrealized=5 >= risk(5) -> breakeven triggers
        (105, 105, 94, 96),      # low=94 would have hit original SL(95), but stop is now 100
    ])
    strat = _BreakevenStrategy(fire_at_bar=1, action="buy", stop_loss=95.0)
    trades, equity, bal = run_backtest(df, strat, _settings())
    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "stop_loss"
    assert trades[0]["exit_price"] == pytest.approx(100.0)  # breakeven, not the original 95
    assert trades[0]["pnl"] >= 0  # breakeven prevented an actual loss


def test_trailing_stop_pct_tightens_and_never_loosens():
    cfg = StrategyConfig(name="t", trailing_stop={"type": "pct", "value": 2.0})
    df = _make_df([
        (100, 101, 99, 100),
        (100, 101, 99, 100),     # signal fires: buy, sl=90
        (100, 120, 99, 118),     # best_price=120 -> trail stop = 120*0.98=117.6 (well above 90)
        (118, 118, 116, 117),    # low=116 <= 117.6 -> stopped out at the TRAILED level
    ])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy", stop_loss=90.0)
    strat.config = cfg
    trades, equity, bal = run_backtest(df, strat, _settings())
    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "stop_loss"
    assert trades[0]["exit_price"] == pytest.approx(117.6, abs=0.01)
    assert trades[0]["exit_price"] > 90.0  # trailed, never fell back to the original stop


def test_time_exit_force_closes_after_configured_bars():
    cfg = StrategyConfig(name="t", time_exit_bars=2)
    df = _make_df([
        (100, 101, 99, 100),
        (100, 101, 99, 100),   # entry bar (bar 1)
        (100, 105, 99, 103),   # bar 2 (1 bar elapsed)
        (103, 106, 102, 104),  # bar 3 (2 bars elapsed) -> time exit fires, closes at this close
        (104, 110, 103, 108),
    ])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy")
    strat.config = cfg
    trades, equity, bal = run_backtest(df, strat, _settings())
    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "time_exit"
    assert trades[0]["exit_price"] == pytest.approx(104.0)  # bar 3's close


# ------------------------------------------------------------ PnL engine

def test_commission_slippage_spread_are_each_independently_nonzero_and_separate():
    df = _make_df([(100, 101, 99, 100), (100, 105, 95, 102), (102, 110, 101, 108)])
    strat = _FixedSignalStrategy(fire_at_bar=1, action="buy")
    settings = _settings(commission_pct=0.1, slippage_pct=0.05, spread_pct=0.02)
    trades, equity, bal = run_backtest(df, strat, settings)
    assert len(trades) == 1
    t = trades[0]
    assert t["commission_cost"] > 0
    assert t["slippage_cost"] > 0
    assert t["spread_cost"] > 0
    # gross_pnl minus commission must equal the reported net pnl exactly
    # (slippage/spread are already embedded in the fill prices that
    # produced gross_pnl, not a second deduction).
    assert t["pnl"] == pytest.approx(t["gross_pnl"] - t["commission_cost"])


def test_no_impossible_position_size_when_balance_exhausted():
    """A stop-loss so tight relative to a tiny balance shouldn't be able to
    produce a negative or infinite size -- it must clamp at 0 once there's
    nothing left to risk."""
    size = _position_size(risk_base=1000.0, available_balance=0.0, entry_price=100.0,
                           stop_loss=99.99, risk_pct=0.01, position_size_pct=0.1)
    assert size == 0.0
    size2 = _position_size(risk_base=1000.0, available_balance=-50.0, entry_price=100.0,
                            stop_loss=99.99, risk_pct=0.01, position_size_pct=0.1)
    assert size2 == 0.0


def test_leverage_raises_the_position_size_cap():
    # No stop-loss -> sizing falls back to position_size_pct of risk_base,
    # capped by available_balance*leverage/entry_price.
    size_1x = _position_size(risk_base=100.0, available_balance=100.0, entry_price=100.0,
                              stop_loss=None, risk_pct=0.01, position_size_pct=10.0, leverage=1.0)
    size_5x = _position_size(risk_base=100.0, available_balance=100.0, entry_price=100.0,
                              stop_loss=None, risk_pct=0.01, position_size_pct=10.0, leverage=5.0)
    assert size_1x == pytest.approx(1.0)   # 100*10/100, capped at balance/price = 1.0
    assert size_5x == pytest.approx(5.0)   # same formula, capped at balance*5/price = 5.0


def test_daily_loss_limit_halts_new_entries_same_day():
    # Tight stop-loss guarantees every entry stops out for a real loss.
    # Same "limited vs unlimited" comparison as the max-drawdown test below
    # -- robust to exactly which trade the threshold is crossed on.
    rows = [(100, 100.5, 99.5, 100)] * 40
    strat_limited = _RepeatingSignalStrategy(action="buy", stop_loss_offset=0.3)
    strat_unlimited = _RepeatingSignalStrategy(action="buy", stop_loss_offset=0.3)
    settings_limited = _settings(daily_loss_limit_pct=1.0, position_size_pct=50.0, risk_pct=5.0)
    settings_unlimited = _settings(position_size_pct=50.0, risk_pct=5.0)
    trades_limited, _, _ = run_backtest(_make_df(rows), strat_limited, settings_limited)
    trades_unlimited, _, _ = run_backtest(_make_df(rows), strat_unlimited, settings_unlimited)
    assert len(trades_limited) > 0
    assert len(trades_limited) < len(trades_unlimited)


def test_max_drawdown_limit_halts_trading_permanently():
    rows = [(100, 100.5, 99.5, 100)] * 60
    df = _make_df(rows)
    strat_limited = _RepeatingSignalStrategy(action="buy", stop_loss_offset=0.3)
    strat_unlimited = _RepeatingSignalStrategy(action="buy", stop_loss_offset=0.3)
    settings_limited = _settings(max_drawdown_limit_pct=2.0, position_size_pct=50.0, risk_pct=5.0)
    settings_unlimited = _settings(position_size_pct=50.0, risk_pct=5.0)
    trades_limited, _, _ = run_backtest(_make_df(rows), strat_limited, settings_limited)
    trades_unlimited, _, _ = run_backtest(_make_df(rows), strat_unlimited, settings_unlimited)
    # With the same losing setup, the circuit breaker must result in
    # strictly fewer trades than letting it run unbounded.
    assert len(trades_limited) < len(trades_unlimited)
