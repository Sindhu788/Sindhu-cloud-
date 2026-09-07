"""One-off builder for New Batch 5, Strategy 2 (Fixed Range Volume Profile /
Market Shape Classification) -- manual construction, no AI extraction."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library, validator


def build():
    cfg = StrategyConfig(
        name="Fixed Range Volume Profile -- Market Shape [Manual Build]",
        raw_text="Fixed Range Volume Profile (FRVP) with Market Shape Classification -- see conversation source document, New Batch 5 Strategy 2.",
        timeframes={"entry": "1h"},
        indicators=[],
        concepts_used=["frvp_hvn_reaction", "frvp_lvn_breakout"],
        entry_rule_groups=[
            {"label": "HVN Support (Long)", "direction": "bullish",
             "conditions": [Condition(type="concept", name="frvp_hvn_reaction", direction="bullish", lookback_bars=1)]},
            {"label": "HVN Resistance (Short)", "direction": "bearish",
             "conditions": [Condition(type="concept", name="frvp_hvn_reaction", direction="bearish", lookback_bars=1)]},
            {"label": "LVN Breakout (Long)", "direction": "bullish",
             "conditions": [Condition(type="concept", name="frvp_lvn_breakout", direction="bullish", lookback_bars=1)]},
            {"label": "LVN Breakout (Short)", "direction": "bearish",
             "conditions": [Condition(type="concept", name="frvp_lvn_breakout", direction="bearish", lookback_bars=1)]},
        ],
        stop_loss=SLTPSpec(type="structure", value=0.65),
        take_profit=SLTPSpec(type="structure"),
        risk_pct=1.0,
        entry_type="market",
        tags=["concept_based_strategy", "manual_build", "frvp_hvn_reaction", "frvp_lvn_breakout", "1h", "new_batch_5"],
    )
    errors = validator.validate(cfg)
    if errors:
        print("VALIDATION FAILED:")
        for e in errors:
            print("  -", e)
        return None
    strategy_id = strategy_library.create(cfg, tags=cfg.tags)
    meta = strategy_library._read_meta(strategy_id)
    print(f"OK -- strategy_id={strategy_id}  safety_status={meta['safety_status']}  name={cfg.name!r}")
    if meta["safety_status"] != "ready":
        print("    safety_reasons:", meta["safety_reasons"])
    return strategy_id


if __name__ == "__main__":
    build()
