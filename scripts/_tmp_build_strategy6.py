"""One-off builder for New Batch 5, Strategy 6 (Order Block Trading) --
manual construction, no AI extraction. Builds Loose and Strict variants."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library, validator


def build(variant):
    concept_name = f"order_block_trading_{variant}"
    label = "Loose" if variant == "loose" else "Strict"
    indicators = []
    if variant == "strict":
        indicators = [
            {"name": "ema", "params": {"period": 200}, "role": "entry"},
            {"name": "ema", "params": {"period": 50}, "role": "entry"},
        ]
    cfg = StrategyConfig(
        name=f"Order Block Trading ({label}) [Manual Build]",
        raw_text="Order Block Trading -- see conversation source document, New Batch 5 Strategy 6.",
        timeframes={"entry": "1h"},
        indicators=indicators,
        # "support"/"resistance" must ALSO be listed here (not just the
        # concept_name) -- ConfiguredStrategy._compute_concept_columns()
        # only computes the generic df["support"]/df["resistance"] columns
        # (the "next significant opposite swing point" target this
        # strategy's own take_profit.type="structure" needs) when one of
        # "support"/"resistance"/"liquidity_sweep" is present in
        # concepts_used -- confirmed missing here first (every trade came
        # back with take_profit=None, a guaranteed-loss-by-construction
        # bug matching this exact failure mode already documented
        # elsewhere in configured_strategy.py's own comments).
        concepts_used=[concept_name, "support", "resistance"],
        long_entry_conditions=[
            Condition(type="concept", name=concept_name, direction="bullish", lookback_bars=1),
        ],
        short_entry_conditions=[
            Condition(type="concept", name=concept_name, direction="bearish", lookback_bars=1),
        ],
        stop_loss=SLTPSpec(type="structure", value=0.65),
        take_profit=SLTPSpec(type="structure"),
        risk_pct=1.0,
        entry_type="market",
        tags=["concept_based_strategy", "manual_build", concept_name, "1h", "new_batch_5"],
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
