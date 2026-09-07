"""One-off builder for New Batch 5, Strategy 1 (Liquidity Sweep + Engulfing
Candle) -- manual construction, no AI extraction. Builds both the LOOSE and
STRICT Confirmation-Strictness variants and saves them to the strategy
library. Run once; safe to delete after running (the saved JSON under
strategies/library/ is the durable artifact, not this script)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library, validator


def build(variant):
    concept_name = f"liquidity_sweep_engulfing_{variant}"
    label = "Loose" if variant == "loose" else "Strict"
    cfg = StrategyConfig(
        name=f"Liquidity Sweep + Engulfing Candle ({label}) [Manual Build]",
        raw_text="Liquidity Sweep + Engulfing Candle -- see conversation source document, New Batch 5 Strategy 1.",
        timeframes={"bias": "4h", "entry": "5m"},
        indicators=[],
        concepts_used=[concept_name, "engulfing"],
        long_entry_conditions=[
            Condition(type="concept", name=concept_name, direction="bullish", lookback_bars=1),
        ],
        short_entry_conditions=[
            Condition(type="concept", name=concept_name, direction="bearish", lookback_bars=1),
        ],
        stop_loss=SLTPSpec(type="structure", value=0.65),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
        entry_type="next_candle_open",
        tags=["concept_based_strategy", "manual_build", concept_name, "5m", "4h", "new_batch_5"],
    )
    errors = validator.validate(cfg)
    if errors:
        print(f"[{label}] VALIDATION FAILED:")
        for e in errors:
            print("  -", e)
        return None
    strategy_id = strategy_library.create(cfg, tags=cfg.tags)
    meta = strategy_library._read_meta(strategy_id)
    print(f"[{label}] OK -- strategy_id={strategy_id}  safety_status={meta['safety_status']}  name={cfg.name!r}")
    if meta["safety_status"] != "ready":
        print("    safety_reasons:", meta["safety_reasons"])
    return strategy_id


if __name__ == "__main__":
    ids = {}
    for variant in ("loose", "strict"):
        sid = build(variant)
        if sid:
            ids[variant] = sid
    print(ids)
