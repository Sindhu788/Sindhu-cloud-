"""Slippage-Aware Entry Filter (Grand Feature Expansion, Phase 5 Feature
8): rejects a real entry when its own recent price volatility suggests
expected slippage would eat too much of the trade's own stop-distance risk
budget. Genuinely distinct from Phase 3's slippage_sensitivity_test
(backtest_engine/slippage_sensitivity.py -- backtest-only, an after-the-
fact PnL recompute on already-CLOSED trades). This runs BEFORE a real
entry, reusing backtest_engine.engine._apply_slippage's exact directional
formula (never re-invented) with a slippage_pct ESTIMATED from the
symbol's own recent 1h candle ranges, rather than the backtest's fixed
assumed constant.

Off by default (feature_toggles.slippage_aware_filter_enabled) -- a brand
new execution-affecting gate, opt-in until the CEO reviews it.
"""

import time

from backtest_engine.engine import _apply_slippage
from data_engine.resample import get_ohlcv

_LOOKBACK_CANDLES = 24
# A full candle's high-low range is a ceiling on intra-hour movement, not a
# realistic single-fill slippage estimate (a real order fills close to the
# current price, not at the extreme of an hour's whole range) -- this
# fraction scales the average range down to a defensible per-fill estimate.
_RANGE_TO_SLIPPAGE_FACTOR = 0.05
MAX_SLIPPAGE_FRACTION_OF_STOP = 0.5  # reject if expected slippage eats over half the stop distance


def estimate_slippage_pct(exchange, symbol):
    """Returns None (not a fabricated number) when there isn't enough
    recent candle history to estimate from -- the filter fails OPEN in
    that case, same 'don't guess, don't block on missing data' convention
    used by every other gated metric in this codebase."""
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - _LOOKBACK_CANDLES * 3600 * 1000
    df = get_ohlcv(exchange, symbol, interval="1h", start_ms=start_ms, end_ms=end_ms)
    if len(df) < 5:
        return None
    ranges_pct = (df["high"] - df["low"]) / df["close"]
    avg_range_pct = float(ranges_pct.mean())
    if avg_range_pct != avg_range_pct:  # NaN guard
        return None
    return avg_range_pct * _RANGE_TO_SLIPPAGE_FACTOR


def check_entry(exchange, symbol, side, entry_price, stop_loss):
    """Returns (ok: bool, reason: str|None, estimated_slippage_pct: float|None)."""
    slippage_pct = estimate_slippage_pct(exchange, symbol)
    if slippage_pct is None:
        return True, None, None
    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0:
        return True, None, slippage_pct
    slipped_entry = _apply_slippage(entry_price, side, False, slippage_pct)
    slippage_amount = abs(slipped_entry - entry_price)
    if slippage_amount > stop_distance * MAX_SLIPPAGE_FRACTION_OF_STOP:
        return False, (
            f"expected slippage (~{slippage_pct * 100:.3f}%) would eat over "
            f"{MAX_SLIPPAGE_FRACTION_OF_STOP * 100:.0f}% of this trade's stop distance"
        ), slippage_pct
    return True, None, slippage_pct
