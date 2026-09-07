"""One-off builder for New Batch 5, Strategy 8 (BOS/CHoCH Structure Break +
Strong Level Retest) -- manual construction, no AI extraction."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library, validator


def build():
    cfg = StrategyConfig(
        name="BOS/CHoCH Structure Break + Strong Level Retest [Manual Build]",
        raw_text="BOS/CHoCH Structure Break + Strong Level Retest -- narrowed, mechanical extraction, see conversation source document, New Batch 5 Strategy 8.",
        timeframes={"entry": "1h"},
        indicators=[],
        concepts_used=["bos_choch_retest"],
        long_entry_conditions=[
            Condition(type="concept", name="bos_choch_retest", direction="bullish", lookback_bars=1),
        ],
        short_entry_conditions=[
            Condition(type="concept", name="bos_choch_retest", direction="bearish", lookback_bars=1),
        ],
        stop_loss=SLTPSpec(type="structure", value=0.65),
        take_profit=SLTPSpec(type="structure"),
        risk_pct=1.0,
        entry_type="market",
        tags=["concept_based_strategy", "manual_build", "bos_choch_retest", "1h", "new_batch_5"],
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
