"""Diagnose why Strategy 2 (FRVP Market Shape) produced 0 trades on BTCUSDT
1h -- per this batch's own rule: a 0-trade result is treated as a possible
bug until checked."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine import strategy_library
from backtest_engine.configured_strategy import ConfiguredStrategy
from backtest_engine.mtf_context import MultiTimeframeContext

sid = "433942cfbbe0"
cfg = strategy_library.load(sid)
strat = ConfiguredStrategy(cfg)

ctx = MultiTimeframeContext("binance", "BTCUSDT", cfg.timeframes, None, None)
df = strat.prepare_context(ctx)
df = strat.prepare(df)

print("rows:", len(df))
print("\nshape value counts:")
print(df["entry_frvp2_shape"].value_counts(dropna=False))

for col in ("entry_frvp_hvn_support_long", "entry_frvp_hvn_resistance_short",
            "entry_frvp_lvn_breakout_long", "entry_frvp_lvn_breakout_short"):
    if col in df.columns:
        print(col, "True count:", int(df[col].sum()))
    else:
        print(col, "MISSING COLUMN")

print("\nnon-null frvp2_poc bars:", df["entry_frvp2_poc"].notna().sum(), "/", len(df))
print("hvn_lo_lo non-null:", df["entry_frvp2_hvn_lo_lo"].notna().sum())
print("hvn_hi_hi non-null:", df["entry_frvp2_hvn_hi_hi"].notna().sum())
print("lvn_lo non-null:", df["entry_frvp2_lvn_lo"].notna().sum())
