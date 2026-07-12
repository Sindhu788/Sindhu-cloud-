"""Aligns multiple timeframes (bias/trend/analysis/entry/confirmation, or any
custom role names) onto a single entry-timeframe index for multi-timeframe
strategies, with zero look-ahead: a higher-timeframe bar's data only becomes
visible starting at the bar that follows it (the moment it actually closes).
"""

import pandas as pd

from data_engine.resample import get_ohlcv


class MultiTimeframeContext:
    def __init__(self, exchange, symbol, timeframes, start_ms=None, end_ms=None):
        """timeframes: {role_name: timeframe_string}, must include "entry".
        Any other role names are strategy-defined (e.g. "bias", "trend",
        "analysis", "confirmation")."""
        if "entry" not in timeframes:
            raise ValueError("timeframes must include an 'entry' role")

        self.exchange = exchange
        self.symbol = symbol
        self.roles = dict(timeframes)
        self.frames = {
            role: get_ohlcv(exchange, symbol, tf, start_ms, end_ms)
            for role, tf in self.roles.items()
        }
        self.merged = None

    def is_empty(self):
        return any(df.empty for df in self.frames.values())

    def build(self):
        """Call once after any indicator columns have been added to
        self.frames[role] (e.g. by a strategy's prepare step). Returns the
        entry-timeframe-indexed merged dataframe: entry_* columns plus, for
        every other role, {role}_* columns holding the most recently CLOSED
        bar's values as of each entry bar."""
        entry_df = self.frames["entry"]
        base = entry_df.add_prefix("entry_").copy()
        base["_ts"] = base.index

        for role, df in self.frames.items():
            if role == "entry" or df.empty:
                continue
            known = df.shift(1).add_prefix(f"{role}_")
            known["_ts"] = known.index
            base = pd.merge_asof(
                base.sort_values("_ts"), known.sort_values("_ts"),
                on="_ts", direction="backward",
            )

        base = base.set_index("_ts")
        base.index.name = entry_df.index.name
        self.merged = base
        return base
