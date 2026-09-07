"""One-off builder for New Batch 5, Strategy 9 (Ichimoku Cloud System) --
manual construction, no AI extraction. Builds all 8 combinations: 4
timeframes (5m/15m/1h/1d) x 2 exit modes (Indicator-Exit/Trailing-SL)."""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library, validator

_TIMEFRAMES = {"5m": "5m", "15m": "15m", "1h": "1h", "1d": "1d"}


def build(tf_label, tf_value, exit_mode):
    exit_label = "Indicator-Exit" if exit_mode == "indicator" else "Trailing-SL"
    name = f"Ichimoku {tf_label} {exit_label} [Manual Build]"

    kwargs = dict(
        name=name,
        raw_text=f"Ichimoku Cloud System, {tf_label} timeframe, {exit_label} variant -- see conversation source document, New Batch 5 Strategy 9.",
        timeframes={"entry": tf_value},
        indicators=[],
        concepts_used=["ichimoku_system"],
        long_entry_conditions=[
            Condition(type="concept", name="ichimoku_system", direction="bullish", lookback_bars=1),
        ],
        short_entry_conditions=[
            Condition(type="concept", name="ichimoku_system", direction="bearish", lookback_bars=1),
        ],
        stop_loss=SLTPSpec(type="structure", value=0.65),
        risk_pct=1.0,
        # Source's own asymmetric execution wording: LONG explicitly
        # "immediately following" the aligned candle; SHORT explicitly "on
        # the candle where all three are fulfilled" (no next-candle delay
        # stated) -- long_entry_type overrides the shared entry_type for
        # longs only, per-direction, exactly as this field is designed for.
        entry_type="market",
        long_entry_type="next_candle_open",
        tags=["concept_based_strategy", "manual_build", "ichimoku_system", tf_value, exit_mode, "new_batch_5"],
    )

    if exit_mode == "indicator":
        kwargs["exit_conditions"] = [
            Condition(type="concept", name="ichimoku_cross", direction="bearish", exit_direction="bullish"),
            Condition(type="concept", name="ichimoku_cross", direction="bullish", exit_direction="bearish"),
        ]
        # Validator requires either a real take_profit or a trailing_stop.
        # A wide 1:10 safety-net RR is NOT this variant's real exit
        # mechanism (the indicator-based exit_conditions above is, and is
        # expected to fire first in the vast majority of trades) -- it only
        # exists to satisfy that schema requirement without silently
        # capping a trend-following exit at an arbitrary tight target.
        kwargs["take_profit"] = SLTPSpec(type="rr", value=10.0)
    else:
        # "Trailing stop-loss instead of the indicator-based exit" --
        # source's own explicitly offered alternative. own default
        # distance (2x ATR(14), source gives no exact number): a
        # configured trailing_stop is itself a valid, complete reason to
        # have no fixed take-profit (validator's own documented rule).
        kwargs["trailing_stop"] = {"type": "atr_multiple", "value": 2.0}

    cfg = StrategyConfig(**kwargs)
    errors = validator.validate(cfg)
    if errors:
        print(f"[{tf_label} {exit_label}] VALIDATION FAILED:")
        for e in errors:
            print("  -", e)
        return None
    strategy_id = strategy_library.create(cfg, tags=cfg.tags)
    meta = strategy_library._read_meta(strategy_id)
    print(f"[{tf_label} {exit_label}] OK -- strategy_id={strategy_id}  safety_status={meta['safety_status']}  name={cfg.name!r}")
    if meta["safety_status"] != "ready":
        print("    safety_reasons:", meta["safety_reasons"])
    return strategy_id


if __name__ == "__main__":
    ids = {}
    for tf_label, tf_value in _TIMEFRAMES.items():
        for exit_mode in ("indicator", "trailing"):
            sid = build(tf_label, tf_value, exit_mode)
            if sid:
                ids[f"{tf_label}_{exit_mode}"] = sid
    print(json.dumps(ids, indent=2))
    with open(os.path.join(os.path.dirname(__file__), "..", "data", "checkpoints", "_strategy9_ids.json"), "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2)
