"""One-off builder for New Batch 5, Strategy 3 (Support/Resistance +
Liquidity Sweep, Sideways Market) -- manual construction, no AI extraction.
Builds both TP variants: Structure (recent high/low) and Fixed-RR (1:2.5
long / 1:2 short)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library, validator


def build(variant):
    label = "Structure" if variant == "structure" else "Fixed-RR"
    concepts_used = ["sr_liquidity_sweep_sideways"]
    if variant == "fixed_rr":
        concepts_used.append("sr_sweep_tp_fixed_rr")
    cfg = StrategyConfig(
        name=f"Support/Resistance + Liquidity Sweep ({label}) [Manual Build]",
        raw_text="Support/Resistance + Liquidity Sweep, Sideways Market -- see conversation source document, New Batch 5 Strategy 3.",
        timeframes={"entry": "1h"},
        indicators=[],
        concepts_used=concepts_used,
        long_entry_conditions=[
            Condition(type="concept", name="sr_liquidity_sweep_sideways", direction="bullish", lookback_bars=1),
        ],
        short_entry_conditions=[
            Condition(type="concept", name="sr_liquidity_sweep_sideways", direction="bearish", lookback_bars=1),
        ],
        stop_loss=SLTPSpec(type="structure", value=0.65),
        take_profit=SLTPSpec(type="structure"),
        risk_pct=1.0,
        entry_type="next_candle_open",
        tags=["concept_based_strategy", "manual_build", "sr_liquidity_sweep_sideways", "1h", "new_batch_5", variant],
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
    for variant in ("structure", "fixed_rr"):
        sid = build(variant)
        if sid:
            ids[variant] = sid
    print(ids)
