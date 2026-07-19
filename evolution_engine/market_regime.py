"""A.8 -- Market regime detection + deterministic parameter adaptation.

Deliberately independent of paper_trading.market_state (which already
detects a regime for live trading) rather than importing it: paper_trading
now imports evolution_engine (position_manager.py, for A.1's lesson
generator), so importing paper_trading back from evolution_engine would
create a package cycle. This module reads OHLCV data directly via
data_engine.resample -- the same primitive backtest_engine.mtf_context
already uses -- and applies its own fixed, deterministic rules. Both
modules deliberately agree on the same four regime labels
(trending_up/trending_down/ranging/volatile) so a BOT strategy's evolution
score and a live paper-trading decision always speak the same vocabulary,
without one module depending on the other.

Pure OHLCV arithmetic (ATR-normalized volatility + windowed % change). No
AI, no ML, no randomness.
"""

from data_engine.resample import get_ohlcv

REGIMES = ["trending_up", "trending_down", "ranging", "volatile"]

HIGH_VOL_ATR_PCT = 2.5      # ATR as % of price at/above this -> "volatile"
TREND_PCT_THRESHOLD = 3.0   # windowed % price change at/beyond this -> trending


def detect_regime(exchange, symbol, timeframe="1h", lookback=100):
    """Returns one of REGIMES, or "unknown" if there isn't enough data yet
    (a brand-new symbol, or an exchange/timeframe combo with no cached
    candles) -- callers must treat "unknown" as "don't adapt, use
    defaults" rather than guessing a regime with no basis."""
    df = get_ohlcv(exchange, symbol, timeframe)
    if df is None or df.empty or len(df) < 20:
        return "unknown"
    recent = df.tail(lookback)
    high, low, close = recent["high"], recent["low"], recent["close"]
    price = float(close.iloc[-1])
    if price <= 0:
        return "unknown"
    true_range = (high - low).rolling(14, min_periods=1).mean()
    atr = float(true_range.iloc[-1])
    volatility_pct = atr / price * 100.0

    first_close = float(close.iloc[0])
    pct_change = ((price - first_close) / first_close * 100.0) if first_close else 0.0

    if volatility_pct >= HIGH_VOL_ATR_PCT:
        return "volatile"
    if pct_change >= TREND_PCT_THRESHOLD:
        return "trending_up"
    if pct_change <= -TREND_PCT_THRESHOLD:
        return "trending_down"
    return "ranging"


# ---- A.8's "adapt BOT strategy parameters accordingly" ----
# A fixed rule table, not a learned one: each regime nudges a small set of
# already-present numeric config fields by a fixed fraction. Only fields the
# strategy already configures are touched (nothing is added that wasn't
# there), and every adaptation is capped to sane bounds so repeated
# adaptation across generations can't run away to an extreme value.
_ADAPTATIONS = {
    "volatile": {"risk_pct": 0.85, "stop_loss_value": 1.15},       # smaller risk, wider stop
    "trending_up": {"risk_reward": 1.15},                           # let winners run further
    "trending_down": {"risk_reward": 1.15},
    "ranging": {"risk_reward": 0.9, "breakeven_at_rr": 0.9},        # take profit sooner, lock in earlier
}

_BOUNDS = {
    "risk_pct": (0.25, 3.0),
    "risk_reward": (0.5, 5.0),
    "breakeven_at_rr": (0.25, 3.0),
    "stop_loss_value": (0.1, 20.0),
}


def _clamp(value, field):
    lo, hi = _BOUNDS[field]
    return max(lo, min(hi, value))


def adapt_params_for_regime(config_dict, regime):
    """config_dict: a StrategyConfig.to_dict(). Returns (adapted_dict,
    changes) where `changes` lists exactly which fields were nudged and by
    what factor, for mutation_reason traceability -- never silently
    mutates. Fields the strategy doesn't already set are left untouched
    (e.g. if breakeven_at_rr is None, "ranging" regime does not invent one)."""
    if regime not in _ADAPTATIONS:
        return config_dict, []
    adapted = dict(config_dict)
    changes = []
    factors = _ADAPTATIONS[regime]

    if "risk_pct" in factors and adapted.get("risk_pct"):
        new_val = round(_clamp(adapted["risk_pct"] * factors["risk_pct"], "risk_pct"), 3)
        changes.append(f"risk_pct {adapted['risk_pct']} -> {new_val} (regime={regime})")
        adapted["risk_pct"] = new_val

    if "risk_reward" in factors and adapted.get("risk_reward"):
        new_val = round(_clamp(adapted["risk_reward"] * factors["risk_reward"], "risk_reward"), 3)
        changes.append(f"risk_reward {adapted['risk_reward']} -> {new_val} (regime={regime})")
        adapted["risk_reward"] = new_val

    if "breakeven_at_rr" in factors and adapted.get("breakeven_at_rr"):
        new_val = round(_clamp(adapted["breakeven_at_rr"] * factors["breakeven_at_rr"], "breakeven_at_rr"), 3)
        changes.append(f"breakeven_at_rr {adapted['breakeven_at_rr']} -> {new_val} (regime={regime})")
        adapted["breakeven_at_rr"] = new_val

    if "stop_loss_value" in factors and adapted.get("stop_loss", {}).get("value"):
        sl = dict(adapted["stop_loss"])
        new_val = round(_clamp(sl["value"] * factors["stop_loss_value"], "stop_loss_value"), 3)
        changes.append(f"stop_loss.value {sl['value']} -> {new_val} (regime={regime})")
        sl["value"] = new_val
        adapted["stop_loss"] = sl

    return adapted, changes
