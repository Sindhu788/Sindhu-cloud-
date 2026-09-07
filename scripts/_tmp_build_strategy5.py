"""One-off builder for New Batch 5, Strategy 5 (FVG Pure + Inverse FVG) --
manual construction, no AI extraction. Builds 2 TP variants: Structure
(recent high/low) and Fixed 1:2."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library, validator

_TP_SPECS = {
    "structure": (SLTPSpec(type="structure"), "Structure"),
    "fixed_2": (SLTPSpec(type="rr", value=2.0), "Fixed 1:2"),
}


def build(variant):
    tp_spec, label = _TP_SPECS[variant]
    cfg = StrategyConfig(
        name=f"FVG Pure + Inverse FVG ({label}) [Manual Build]",
        raw_text="FVG Pure + Inverse FVG -- see conversation source document, New Batch 5 Strategy 5.",
        timeframes={"entry": "1h"},
        indicators=[],
        concepts_used=["fvg_pure_inverse"],
        long_entry_conditions=[
            Condition(type="concept", name="fvg_pure_inverse", direction="bullish", lookback_bars=1),
        ],
        short_entry_conditions=[
            Condition(type="concept", name="fvg_pure_inverse", direction="bearish", lookback_bars=1),
        ],
        stop_loss=SLTPSpec(type="structure", value=0.65),
        take_profit=tp_spec,
        risk_pct=1.0,
        entry_type="market",
        tags=["concept_based_strategy", "manual_build", "fvg_pure_inverse", "1h", "new_batch_5", variant],
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
    for variant in ("structure", "fixed_2"):
        sid = build(variant)
        if sid:
            ids[variant] = sid
    print(ids)
