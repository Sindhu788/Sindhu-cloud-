"""Turns a parsed StrategyConfig into something engine.run_backtest can run,
without hand-writing a Strategy subclass per strategy. All indicator/concept
math comes from concepts.py; this class only wires config -> columns ->
Signal.
"""

import pandas as pd

from strategies.base import Strategy, Signal
from backtest_engine import concepts

_DEFAULT_PERIOD = {"ema": 20, "sma": 20, "rsi": 14, "atr": 14}


class ConfiguredStrategy(Strategy):
    def __init__(self, config):
        self.config = config
        self.name = config.name

    # -------------------------------------------------- multi-timeframe prep
    def prepare_context(self, ctx):
        """Call once per symbol before engine.run_backtest: computes every
        referenced indicator on each role's native-resolution frame (so a
        4H EMA is a real 4H EMA, not one computed on upsampled data), then
        merges everything onto the entry timeframe."""
        for ind in self.config.indicators:
            role = ind.get("role") or "entry"
            df = ctx.frames.get(role)
            if df is None or df.empty:
                continue
            name = ind["name"]
            period = ind["params"].get("period") or _DEFAULT_PERIOD.get(name)
            if name == "ema" and f"ema_{period}" not in df.columns:
                df[f"ema_{period}"] = concepts.ema(df["close"], period)
            elif name == "sma" and f"sma_{period}" not in df.columns:
                df[f"sma_{period}"] = concepts.sma(df["close"], period)
            elif name == "rsi" and f"rsi_{period}" not in df.columns:
                df[f"rsi_{period}"] = concepts.rsi(df["close"], period)
            elif name == "atr" and f"atr_{period}" not in df.columns:
                df[f"atr_{period}"] = concepts.atr(df, period)

        entry_df = ctx.frames.get("entry")
        if entry_df is not None and not entry_df.empty:
            used = set(self.config.concepts_used)
            if "bos" in used or "choch" in used:
                entry_df["bull_bos"], entry_df["bear_bos"] = concepts.break_of_structure(entry_df)
            if "choch" in used:
                entry_df["bull_choch"], entry_df["bear_choch"] = concepts.change_of_character(entry_df)
            if "fvg" in used:
                entry_df["bull_fvg"], entry_df["bear_fvg"] = concepts.fair_value_gap(entry_df)
            if "order_block" in used or "breaker_block" in used:
                bl, bh, brl, brh = concepts.order_blocks(entry_df)
                entry_df["bull_ob_low"], entry_df["bull_ob_high"] = bl, bh
                entry_df["bear_ob_low"], entry_df["bear_ob_high"] = brl, brh
            if "breaker_block" in used:
                bbl, bbh, brbl, brbh = concepts.breaker_blocks(entry_df)
                entry_df["bull_breaker_low"], entry_df["bull_breaker_high"] = bbl, bbh
                entry_df["bear_breaker_low"], entry_df["bear_breaker_high"] = brbl, brbh
            if "support" in used or "resistance" in used or "liquidity_sweep" in used:
                entry_df["support"], entry_df["resistance"] = concepts.support_resistance(entry_df)
            if "liquidity_sweep" in used:
                entry_df["bull_liquidity_sweep"], entry_df["bear_liquidity_sweep"] = concepts.liquidity_sweep(entry_df)
            if "volume" in used and "volume_spike" not in entry_df.columns:
                entry_df["volume_spike"] = concepts.volume_filter(entry_df)
            if {"pdh", "pdl", "pdh_sweep", "pdl_sweep"} & used:
                entry_df["pdh"], entry_df["pdl"] = concepts.previous_day_high_low(entry_df)
            if {"pdh_sweep", "pdl_sweep"} & used:
                entry_df["pdl_sweep"], entry_df["pdh_sweep"] = concepts.pdh_pdl_sweep(entry_df)
            if "fvg" in used and self.config.stop_loss.type == "structure":
                (entry_df["fvg_bull_low"], entry_df["fvg_bull_high"],
                 entry_df["fvg_bear_low"], entry_df["fvg_bear_high"]) = concepts.fvg_zone(entry_df)
            if self.config.session_filter:
                entry_df["session"] = concepts.session_column(entry_df)
            if self.config.trend_filter:
                entry_df["trend_dir"] = concepts.trend_filter(entry_df)
            if self.config.stop_loss.type == "atr_multiple" or self.config.take_profit.type == "atr_multiple":
                if "atr_14" not in entry_df.columns:
                    entry_df["atr_14"] = concepts.atr(entry_df, 14)

        return ctx.build()

    # -------------------------------------------------- Strategy interface
    def prepare(self, df):
        # engine.run_backtest expects plain open/high/low/close/volume
        # columns; alias them from the entry timeframe's prefixed columns
        # so the existing (unmodified) engine works unchanged.
        for col in ("open", "high", "low", "close", "volume"):
            entry_col = f"entry_{col}"
            if entry_col in df.columns and col not in df.columns:
                df[col] = df[entry_col]
        return df

    def on_bar(self, df, i, position):
        cfg = self.config

        if position is None:
            if not cfg.entry_conditions:
                return None
            entry_ok = all(self._eval(c, df, i) for c in cfg.entry_conditions)
            if entry_ok and cfg.confirmation_conditions:
                entry_ok = all(self._eval(c, df, i) for c in cfg.confirmation_conditions)
            if entry_ok and cfg.session_filter:
                session_val = df["entry_session"].iloc[i] if "entry_session" in df.columns else None
                entry_ok = session_val in cfg.session_filter
            if entry_ok and cfg.trend_filter and "entry_trend_dir" in df.columns:
                entry_ok = df["entry_trend_dir"].iloc[i] == cfg.trend_filter

            if not entry_ok:
                return None

            direction = self._infer_direction()
            price = df["close"].iloc[i]
            sl = self._compute_stop_loss(df, i, price, direction)
            tp = self._compute_take_profit(df, i, price, direction, sl)
            action = "buy" if direction == "bullish" else "sell"
            return Signal(action=action, stop_loss=sl, take_profit=tp, reason=self._describe(cfg.entry_conditions))

        else:
            if cfg.exit_conditions and all(self._eval(c, df, i) for c in cfg.exit_conditions):
                return Signal(action="exit", reason=self._describe(cfg.exit_conditions))
            return None

    # -------------------------------------------------- helpers
    def _infer_direction(self):
        for c in self.config.entry_conditions:
            if c.direction in ("bullish", "bearish"):
                return c.direction
        return "bullish"

    def _indicator_column(self, indicator_name, params):
        period = params.get("period")
        role = "entry"
        resolved_period = period
        for ind in self.config.indicators:
            if ind["name"] == indicator_name and (period is None or ind["params"].get("period") == period):
                role = ind.get("role") or "entry"
                resolved_period = ind["params"].get("period", period)
                break
        resolved_period = resolved_period or _DEFAULT_PERIOD.get(indicator_name, 14)
        if indicator_name in ("ema", "sma", "rsi", "atr"):
            return f"{role}_{indicator_name}_{resolved_period}"
        return f"{role}_{indicator_name}"

    def _get(self, df, i, col):
        if col not in df.columns:
            return None
        val = df[col].iloc[i]
        return None if pd.isna(val) else val

    def _eval(self, cond, df, i):
        if cond.type == "raw":
            return False

        if cond.type == "concept":
            # Problem 2 (Phase 6): event-like concepts (BOS/CHoCH/FVG/volume
            # spike/PDH-PDL sweep) don't have to have fired on this EXACT
            # bar -- real strategies are sequences ("sweep, THEN BOS, THEN
            # FVG"). Default window is 10 bars; a condition can override it
            # ("within 20 bars") or force strict same-bar (lookback_bars=1,
            # the original behavior) via the parser. Only ever looks
            # backward from bar i, so zero look-ahead is unchanged.
            window = cond.lookback_bars if cond.lookback_bars is not None else 10

            def _within(col):
                if col not in df.columns:
                    return False
                return concepts.true_within_lookback(df[col], i, window)

            event_colmap = {
                "bos": ("entry_bull_bos", "entry_bear_bos"),
                "choch": ("entry_bull_choch", "entry_bear_choch"),
                "fvg": ("entry_bull_fvg", "entry_bear_fvg"),
                "liquidity_sweep": ("entry_bull_liquidity_sweep", "entry_bear_liquidity_sweep"),
            }
            if cond.name in event_colmap:
                bull_col, bear_col = event_colmap[cond.name]
                if cond.direction == "bearish":
                    return _within(bear_col)
                if cond.direction == "bullish":
                    return _within(bull_col)
                return _within(bull_col) or _within(bear_col)
            if cond.name in ("pdh_sweep", "pdl_sweep"):
                return _within(f"entry_{cond.name}")
            if cond.name == "order_block":
                return self._get(df, i, "entry_bull_ob_low") is not None or self._get(df, i, "entry_bear_ob_low") is not None
            if cond.name == "breaker_block":
                return self._get(df, i, "entry_bull_breaker_low") is not None or self._get(df, i, "entry_bear_breaker_low") is not None
            if cond.name == "support":
                price = self._get(df, i, "close")
                support = self._get(df, i, "entry_support")
                return price is not None and support is not None and abs(price - support) / price < 0.005
            if cond.name == "resistance":
                price = self._get(df, i, "close")
                resistance = self._get(df, i, "entry_resistance")
                return price is not None and resistance is not None and abs(price - resistance) / price < 0.005
            if cond.name == "volume":
                return _within("entry_volume_spike")
            if cond.name in ("pdh", "pdl"):
                return self._get(df, i, f"entry_{cond.name}") is not None
            return False

        if cond.type == "indicator_compare":
            col = self._indicator_column(cond.indicator, cond.params)
            val = self._get(df, i, col)
            if val is None:
                return False
            ops = {"<": val < cond.value, ">": val > cond.value,
                   "<=": val <= cond.value, ">=": val >= cond.value}
            return ops.get(cond.op, False)

        if cond.type == "price_compare":
            price = self._get(df, i, "close")
            ind_val = self._get(df, i, self._indicator_column(cond.indicator, cond.params))
            if price is None or ind_val is None:
                return False
            return price > ind_val if cond.op == ">" else price < ind_val

        if cond.type == "session":
            return self._get(df, i, "entry_session") == cond.name

        if cond.type == "trend":
            return self._get(df, i, "entry_trend_dir") == cond.direction

        return False

    def _compute_stop_loss(self, df, i, price, direction):
        spec = self.config.stop_loss
        if spec.type == "fixed_pct" and spec.value is not None:
            pct = spec.value / 100.0
            return price * (1 - pct) if direction == "bullish" else price * (1 + pct)
        if spec.type == "atr_multiple" and spec.value is not None:
            atr_val = self._get(df, i, "entry_atr_14")
            if atr_val is None:
                return None
            return price - spec.value * atr_val if direction == "bullish" else price + spec.value * atr_val
        if spec.type == "structure":
            # Priority order: order block zone, then FVG zone, then plain
            # support/resistance -- whichever structural anchor is actually
            # available on this bar. Same priority for every strategy,
            # doesn't depend on which specific word the CEO used.
            if direction == "bullish":
                zone = self._get(df, i, "entry_bull_ob_low")
                if zone is None:
                    zone = self._get(df, i, "entry_fvg_bull_low")
                if zone is None:
                    zone = self._get(df, i, "entry_support")
                return zone
            else:
                zone = self._get(df, i, "entry_bear_ob_high")
                if zone is None:
                    zone = self._get(df, i, "entry_fvg_bear_high")
                if zone is None:
                    zone = self._get(df, i, "entry_resistance")
                return zone
        return None

    def _compute_take_profit(self, df, i, price, direction, sl):
        spec = self.config.take_profit
        if spec.type == "fixed_pct" and spec.value is not None:
            pct = spec.value / 100.0
            return price * (1 + pct) if direction == "bullish" else price * (1 - pct)
        if spec.type == "rr" and spec.value is not None:
            if sl is None:
                return None
            risk_distance = abs(price - sl)
            return price + risk_distance * spec.value if direction == "bullish" else price - risk_distance * spec.value
        if spec.type == "atr_multiple" and spec.value is not None:
            atr_val = self._get(df, i, "entry_atr_14")
            if atr_val is None:
                return None
            return price + spec.value * atr_val if direction == "bullish" else price - spec.value * atr_val
        if spec.type == "level" and spec.level:
            return self._get(df, i, f"entry_{spec.level}")
        return None

    def _describe(self, conditions):
        parts = []
        for c in conditions:
            if c.type == "concept":
                parts.append(f"{(c.direction + ' ') if c.direction else ''}{c.name}".strip())
            elif c.type == "indicator_compare":
                parts.append(f"{c.indicator} {c.op} {c.value}")
            elif c.type == "price_compare":
                parts.append(f"price {c.op} {c.indicator}")
            elif c.type == "session":
                parts.append(f"session={c.name}")
            elif c.type == "trend":
                parts.append(f"trend={c.direction}")
            else:
                parts.append(c.text or "condition")
        return " + ".join(parts) if parts else "signal"
