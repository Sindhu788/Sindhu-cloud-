"""One-off builder for New Batch 5, Strategy 7 (Candle Range Theory / CRT)
-- manual construction, no AI extraction. Builds Loose and Strict variants."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library, validator


def build(variant):
    concept_name = f"crt_{variant}"
    label = "Loose" if variant == "loose" else "Strict"
    indicators = []
    if variant == "strict":
        indicators = [
            {"name": "ema", "params": {"period": 200}, "role": "entry"},
            {"name": "ema", "params": {"period": 50}, "role": "entry"},
        ]
    cfg = StrategyConfig(
        name=f"Candle Range Theory ({label}) [Manual Build]",
        raw_text="Candle Range Theory (CRT) -- see conversation source document, New Batch 5 Strategy 7.",
        timeframes={"entry": "1h"},
        indicators=indicators,
        concepts_used=[concept_name],
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
