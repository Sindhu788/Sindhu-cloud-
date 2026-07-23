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
        self._arr_cache = {}
        # Phase 2 (Strategy Verification Engine, BACKTESTING_MASTER_SPEC.md
        # Requirement 13): an optional trace hook, off by default (a single
        # `if self._trace:` check has no measurable cost on the hot path).
        # backtest_engine.strategy_verifier sets this to a callback that
        # records "this exact Condition object was evaluated, with this
        # result" so a verification run can prove every rule in the saved
        # JSON actually gets reached by the Rule Engine, instead of only
        # trusting that it should.
        self._trace = None

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
            elif name == "vwap" and "vwap" not in df.columns:
                # Was declared usable (validator._KNOWN_INDICATORS, the AI
                # schema) and concepts.vwap_daily() already existed, but was
                # never actually wired in here -- any "price vs vwap"
                # condition silently evaluated False forever. Same period-less
                # shape as the other indicators; _indicator_column() already
                # falls back to a bare "{role}_vwap" column name for it.
                df["vwap"] = concepts.vwap_daily(df)

        entry_df = ctx.frames.get("entry")
        if entry_df is not None and not entry_df.empty:
            used = set(self.config.concepts_used)
            self._compute_concept_columns(entry_df, used)
            if self.config.session_filter:
                entry_df["session"] = concepts.session_column(entry_df)
            if self.config.trend_filter:
                entry_df["trend_dir"] = concepts.trend_filter(entry_df)
            if self.config.day_filter:
                entry_df["day_of_week"] = concepts.day_of_week_column(entry_df)
            if self.config.stop_loss.type == "atr_multiple" or self.config.take_profit.type == "atr_multiple":
                if "atr_14" not in entry_df.columns:
                    entry_df["atr_14"] = concepts.atr(entry_df, 14)

            # Bug fix: every structural/event concept (BOS, CHoCH, FVG, order
            # block, liquidity sweep, swing points, ...) used to be computed
            # ONLY on the entry (typically 1-minute) frame, no matter which
            # role a strategy actually declared for it -- Condition.role
            # exists in the schema but was dead code end-to-end. A strategy
            # explicitly describing "a significant swing low on the 1H or 4H
            # chart" (e.g. "Liquidity Sweeps") silently got noisy 1-minute
            # micro-pivots instead, which is a big part of why its trade
            # count and win rate were both so bad -- confirmed via a real
            # audit re-run (see PROGRESS.md). Any OTHER role a condition
            # explicitly names now gets the SAME concept columns computed on
            # ITS OWN native-resolution frame (not upsampled/downsampled
            # entry data), exactly like indicators already do above --
            # ctx.build() below already knows how to causally align a
            # non-entry role's columns onto the entry index (shift +
            # backward-asof), so nothing else needs to change for this to
            # flow through correctly. A condition with role=None (every
            # strategy saved before this fix, and any strategy that simply
            # doesn't specify one) is completely unaffected -- it still only
            # ever reads the entry_ prefixed columns above.
            for role in self._condition_roles():
                if role in (None, "entry"):
                    continue
                role_df = ctx.frames.get(role)
                if role_df is None or role_df.empty:
                    continue
                self._compute_concept_columns(role_df, used)

        return ctx.build()

    def _condition_roles(self):
        roles = set()
        for bucket in (self.config.entry_conditions, self.config.exit_conditions, self.config.confirmation_conditions):
            for cond in bucket:
                if cond.type == "concept" and cond.role:
                    roles.add(cond.role)
        return roles

    @staticmethod
    def _compute_concept_columns(df, used):
        """Computes every concept-derived column `used` calls for, directly
        on `df` -- shared by the entry timeframe (always) and any other role
        a condition explicitly references (see prepare_context)."""
        if "bos" in used or "choch" in used:
            df["bull_bos"], df["bear_bos"] = concepts.break_of_structure(df)
        if "choch" in used:
            df["bull_choch"], df["bear_choch"] = concepts.change_of_character(df)
        if "fvg" in used:
            df["bull_fvg"], df["bear_fvg"] = concepts.fair_value_gap(df)
        if "order_block" in used or "breaker_block" in used:
            bl, bh, brl, brh = concepts.order_blocks(df)
            df["bull_ob_low"], df["bull_ob_high"] = bl, bh
            df["bear_ob_low"], df["bear_ob_high"] = brl, brh
        if "breaker_block" in used:
            bbl, bbh, brbl, brbh = concepts.breaker_blocks(df)
            df["bull_breaker_low"], df["bull_breaker_high"] = bbl, bbh
            df["bear_breaker_low"], df["bear_breaker_high"] = brbl, brbh
        if "support" in used or "resistance" in used or "liquidity_sweep" in used:
            df["support"], df["resistance"] = concepts.support_resistance(df)
        if "liquidity_sweep" in used:
            df["bull_liquidity_sweep"], df["bear_liquidity_sweep"] = concepts.liquidity_sweep(df)
        if "candle_break" in used:
            df["bull_candle_break"], df["bear_candle_break"] = concepts.candle_break(df)
        if "volume" in used and "volume_spike" not in df.columns:
            df["volume_spike"] = concepts.volume_filter(df)
        if {"pdh", "pdl", "pdh_sweep", "pdl_sweep"} & used:
            df["pdh"], df["pdl"] = concepts.previous_day_high_low(df)
        if {"pdh_sweep", "pdl_sweep"} & used:
            df["pdl_sweep"], df["pdh_sweep"] = concepts.pdh_pdl_sweep(df)
        if "fvg" in used:
            (df["fvg_bull_low"], df["fvg_bull_high"],
             df["fvg_bear_low"], df["fvg_bear_high"]) = concepts.fvg_zone(df)
        if {"poc", "value_area"} & used:
            df["poc"], df["vah"], df["val"] = concepts.volume_profile_previous_day(df)
        if {"lvn", "hvn"} & used:
            df["in_lvn"], df["in_hvn"] = concepts.volume_nodes_previous_day(df)
        if "aggression" in used:
            df["bull_aggression"], df["bear_aggression"] = concepts.aggression(df)
        if "mitigation_block" in used:
            mbl, mbh, mrbl, mrbh = concepts.mitigation_blocks(df)
            df["bull_mitigation_low"], df["bull_mitigation_high"] = mbl, mbh
            df["bear_mitigation_low"], df["bear_mitigation_high"] = mrbl, mrbh
        if "imbalance" in used:
            df["bull_imbalance"], df["bear_imbalance"] = concepts.imbalance(df)
        if "equal_highs_lows" in used:
            df["bull_equal_lows"], df["bear_equal_highs"] = concepts.equal_highs_lows(df)
        if {"swing_high", "swing_low"} & used:
            df["swing_high_event"], df["swing_low_event"] = concepts.swing_points(df)
        if "session_high_low" in used:
            df["session_high"], df["session_low"] = concepts.session_high_low(df)
        if "session_open" in used:
            df["session_open"] = concepts.session_open_price(df)
        if "engulfing" in used:
            df["bull_engulfing"], df["bear_engulfing"] = concepts.engulfing_candle(df)
        if "pin_bar" in used:
            df["bull_pin_bar"], df["bear_pin_bar"] = concepts.pin_bar(df)
        if "inside_bar" in used:
            df["inside_bar"] = concepts.inside_bar(df)

    # -------------------------------------------------- Strategy interface
    def prepare(self, df):
        # engine.run_backtest expects plain open/high/low/close/volume
        # columns; alias them from the entry timeframe's prefixed columns
        # so the existing (unmodified) engine works unchanged.
        for col in ("open", "high", "low", "close", "volume"):
            entry_col = f"entry_{col}"
            if entry_col in df.columns and col not in df.columns:
                df[col] = df[entry_col]
        # Fresh per run: on_bar is called hundreds of thousands of times
        # against this same `df`, so every column it touches is converted to
        # a plain numpy array once (via _array()) instead of re-slicing a
        # pandas Series on every single bar -- profiling a real backtest
        # showed pandas Series.iloc/slicing overhead (Index rebuilding,
        # __finalize__, metadata propagation) was the dominant cost, not the
        # actual condition math. Numpy array indexing returns the exact same
        # values, just without that overhead.
        self._arr_cache = {}
        return df

    def _array(self, df, col):
        arr = self._arr_cache.get(col)
        if arr is None:
            if col not in df.columns:
                return None
            arr = df[col].to_numpy()
            self._arr_cache[col] = arr
        return arr

    def on_bar(self, df, i, position):
        cfg = self.config

        if position is None:
            # Two mutually-exclusive rule sets (a strategy with separate
            # "Long Entry Rules"/"Short Entry Rules" sections) take priority
            # over the legacy single entry_conditions gate whenever either is
            # populated. A strategy that only ever fills entry_conditions
            # (every strategy saved before this feature existed) falls
            # through to the unchanged legacy branch below.
            if cfg.long_entry_conditions or cfg.short_entry_conditions:
                direction, matched_conditions = self._eval_long_short(df, i)
                entry_ok = direction is not None
            else:
                if not cfg.entry_conditions:
                    return None
                entry_ok = all(self._eval_traced(c, df, i) for c in cfg.entry_conditions)
                direction = self._infer_direction() if entry_ok else None
                matched_conditions = cfg.entry_conditions

            if entry_ok and cfg.confirmation_conditions:
                entry_ok = all(self._eval_traced(c, df, i) for c in cfg.confirmation_conditions)
            if entry_ok and cfg.session_filter:
                session_val = df["entry_session"].iloc[i] if "entry_session" in df.columns else None
                entry_ok = session_val in cfg.session_filter
            if entry_ok and cfg.trend_filter and "entry_trend_dir" in df.columns:
                entry_ok = df["entry_trend_dir"].iloc[i] == cfg.trend_filter

            if not entry_ok:
                return None

            price = self._array(df, "close")[i]
            sl = self._compute_stop_loss(df, i, price, direction)
            tp = self._compute_take_profit(df, i, price, direction, sl)
            action = "buy" if direction == "bullish" else "sell"
            return Signal(action=action, stop_loss=sl, take_profit=tp, reason=self._describe(matched_conditions))

        else:
            if cfg.exit_conditions and all(self._eval_traced(c, df, i) for c in cfg.exit_conditions):
                return Signal(action="exit", reason=self._describe(cfg.exit_conditions))
            return None

    def _eval_long_short(self, df, i):
        """Returns (direction, matched_conditions) for whichever rule set is
        satisfied at this bar, or (None, None) if neither is -- or if BOTH
        somehow are (a genuinely contradictory bar), which is treated as no
        signal rather than an arbitrary guess about which side to take."""
        cfg = self.config
        long_ok = bool(cfg.long_entry_conditions) and all(self._eval_traced(c, df, i) for c in cfg.long_entry_conditions)
        short_ok = bool(cfg.short_entry_conditions) and all(self._eval_traced(c, df, i) for c in cfg.short_entry_conditions)
        if long_ok and short_ok:
            return None, None
        if long_ok:
            return "bullish", cfg.long_entry_conditions
        if short_ok:
            return "bearish", cfg.short_entry_conditions
        return None, None

    def manage_position(self, df, i, position):
        """Break-even stop-move: if configured (breakeven_at_rr), moves
        position["stop_loss"] to entry_price once unrealized profit
        reaches that many multiples of the ORIGINAL risk. Tracks the
        original stop separately (position["_original_stop"]) the first
        time this runs for a position, since stop_loss itself gets
        overwritten once moved -- otherwise a second call would compute
        risk against the already-moved (zero-distance) stop and never
        trigger correctly again."""
        trigger_rr = self.config.breakeven_at_rr
        if trigger_rr is None:
            return
        if "_original_stop" not in position:
            position["_original_stop"] = position["stop_loss"]
        price = self._array(df, "close")[i]
        direction = "bullish" if position["side"] == "long" else "bearish"
        new_stop = concepts.breakeven_stop(
            position["entry_price"], position["_original_stop"], price, direction, trigger_rr,
        )
        if new_stop is not None:
            position["stop_loss"] = new_stop

    # -------------------------------------------------- helpers
    def _infer_direction(self):
        for c in self.config.entry_conditions:
            if c.direction in ("bullish", "bearish"):
                return c.direction
        return "bullish"

    def _indicator_column(self, indicator_name, params, cond_role=None):
        period = params.get("period")
        resolved_period = period
        role = None
        if cond_role:
            # The condition itself says which timeframe it means -- this is
            # authoritative and disambiguates a strategy that declares the
            # SAME indicator name on more than one role (e.g. an sma on
            # both "trend" and "analysis"), which the name+period lookup
            # below can't reliably do: two same-named indicators with no
            # period specified on the condition would otherwise just match
            # whichever happens to be first in config.indicators.
            for ind in self.config.indicators:
                if (ind["name"] == indicator_name and (ind.get("role") or "entry") == cond_role
                        and (period is None or ind["params"].get("period") == period)):
                    resolved_period = ind["params"].get("period", period)
                    break
            role = cond_role
        if role is None:
            role = "entry"
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
        arr = self._array(df, col)
        if arr is None:
            return None
        val = arr[i]
        return None if pd.isna(val) else val

    def _eval_traced(self, cond, df, i):
        """Same as _eval(), plus an optional trace callback (see __init__)
        -- kept as a thin wrapper around the real evaluator rather than
        instrumenting _eval() internally, so tracing can never change what
        a condition evaluates to, only observe it."""
        result = self._eval(cond, df, i)
        if self._trace is not None:
            self._trace(cond, result)
        return result

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
            # Bug fix: was hardcoded to "entry_" regardless of cond.role, so
            # a condition explicitly tagged for a higher-timeframe role (see
            # prepare_context/_compute_concept_columns) still silently read
            # the entry-timeframe column. role=None (every strategy saved
            # before this fix) still resolves to "entry", unchanged.
            role = cond.role or "entry"

            def _rcol(name):
                return f"{role}_{name}"

            def _within(col):
                # Same math as concepts.true_within_lookback(), just against
                # the cached numpy array instead of a pandas Series -- see
                # the note in prepare() for why.
                arr = self._array(df, col)
                if arr is None:
                    return False
                start = max(0, i - window + 1)
                return bool(arr[start:i + 1].any())

            event_colmap = {
                "bos": (_rcol("bull_bos"), _rcol("bear_bos")),
                "choch": (_rcol("bull_choch"), _rcol("bear_choch")),
                "fvg": (_rcol("bull_fvg"), _rcol("bear_fvg")),
                "liquidity_sweep": (_rcol("bull_liquidity_sweep"), _rcol("bear_liquidity_sweep")),
                "candle_break": (_rcol("bull_candle_break"), _rcol("bear_candle_break")),
                "aggression": (_rcol("bull_aggression"), _rcol("bear_aggression")),
                "imbalance": (_rcol("bull_imbalance"), _rcol("bear_imbalance")),
                "equal_highs_lows": (_rcol("bull_equal_lows"), _rcol("bear_equal_highs")),
                "engulfing": (_rcol("bull_engulfing"), _rcol("bear_engulfing")),
                "pin_bar": (_rcol("bull_pin_bar"), _rcol("bear_pin_bar")),
            }
            if cond.name in event_colmap:
                bull_col, bear_col = event_colmap[cond.name]
                if cond.direction == "bearish":
                    return _within(bear_col)
                if cond.direction == "bullish":
                    return _within(bull_col)
                return _within(bull_col) or _within(bear_col)
            if cond.name in ("pdh_sweep", "pdl_sweep"):
                return _within(_rcol(cond.name))
            if cond.name == "order_block":
                return self._get(df, i, _rcol("bull_ob_low")) is not None or self._get(df, i, _rcol("bear_ob_low")) is not None
            if cond.name == "breaker_block":
                return self._get(df, i, _rcol("bull_breaker_low")) is not None or self._get(df, i, _rcol("bear_breaker_low")) is not None
            if cond.name == "support":
                price = self._get(df, i, "close")
                support = self._get(df, i, _rcol("support"))
                return price is not None and support is not None and abs(price - support) / price < 0.005
            if cond.name == "resistance":
                price = self._get(df, i, "close")
                resistance = self._get(df, i, _rcol("resistance"))
                return price is not None and resistance is not None and abs(price - resistance) / price < 0.005
            if cond.name == "volume":
                return _within(_rcol("volume_spike"))
            if cond.name in ("pdh", "pdl"):
                # A bare "pdh"/"pdl" reference means the strategy is gating
                # on the actual price-vs-level relationship ("price above
                # PDH" / "price below PDL") -- exactly like every other
                # level-type concept in this function (support, resistance,
                # poc, value_area, session_high_low) does a real comparison
                # rather than a bare existence check. Before this fix it only
                # checked whether the level was DEFINED, which is true for
                # essentially the entire trading day, every day -- making the
                # condition a permanent no-op that silently dropped the
                # strategy's actual filter (confirmed: PDH-PDL Signal Candle
                # Strategy's "price must trade above PDH" rule never
                # constrained anything, inflating its trade count into the
                # tens of thousands). "sweep of pdh/pdl" is a separate,
                # already-correct event concept (pdh_sweep/pdl_sweep, above)
                # and is unaffected by this branch.
                price = self._get(df, i, "close")
                level = self._get(df, i, _rcol(cond.name))
                if price is None or level is None:
                    return False
                return price > level if cond.name == "pdh" else price < level
            if cond.name == "mitigation_block":
                return self._get(df, i, _rcol("bull_mitigation_low")) is not None or self._get(df, i, _rcol("bear_mitigation_low")) is not None
            if cond.name == "poc":
                price = self._get(df, i, "close")
                poc = self._get(df, i, _rcol("poc"))
                return price is not None and poc is not None and abs(price - poc) / price < 0.005
            if cond.name == "value_area":
                price = self._get(df, i, "close")
                vah = self._get(df, i, _rcol("vah"))
                val = self._get(df, i, _rcol("val"))
                return price is not None and vah is not None and val is not None and val <= price <= vah
            if cond.name == "lvn":
                return bool(self._get(df, i, _rcol("in_lvn")))
            if cond.name == "hvn":
                return bool(self._get(df, i, _rcol("in_hvn")))
            if cond.name == "swing_high":
                return _within(_rcol("swing_high_event"))
            if cond.name == "swing_low":
                return _within(_rcol("swing_low_event"))
            if cond.name == "session_high_low":
                price = self._get(df, i, "close")
                session_high = self._get(df, i, _rcol("session_high"))
                session_low = self._get(df, i, _rcol("session_low"))
                if price is None:
                    return False
                near_high = session_high is not None and abs(price - session_high) / price < 0.005
                near_low = session_low is not None and abs(price - session_low) / price < 0.005
                if cond.direction == "bullish":
                    return near_low
                if cond.direction == "bearish":
                    return near_high
                return near_high or near_low
            if cond.name == "session_open":
                price = self._get(df, i, "close")
                session_open = self._get(df, i, _rcol("session_open"))
                return price is not None and session_open is not None and abs(price - session_open) / price < 0.005
            if cond.name == "inside_bar":
                return bool(self._get(df, i, _rcol("inside_bar")))
            return False

        if cond.type == "indicator_compare":
            col = self._indicator_column(cond.indicator, cond.params, cond.role)
            val = self._get(df, i, col)
            # cond.value is required for this type (it's what val gets
            # compared against) -- a condition can reach here with it
            # missing/None if something upstream saved one without it
            # (found live: the AI-native builder let an indicator-vs-
            # indicator comparison, e.g. "ema20 > ema50", through with no
            # value since that comparison genuinely isn't representable by
            # this type, instead of demoting it to type="raw" like every
            # other unrepresentable rule). Building the ops dict below
            # evaluates every comparison eagerly regardless of cond.op, so
            # `val < None` would raise TypeError even though "<" was never
            # the requested operator -- guard before that, not after.
            if val is None or cond.value is None:
                return False
            ops = {"<": val < cond.value, ">": val > cond.value,
                   "<=": val <= cond.value, ">=": val >= cond.value}
            return ops.get(cond.op, False)

        if cond.type == "price_compare":
            price = self._get(df, i, "close")
            ind_val = self._get(df, i, self._indicator_column(cond.indicator, cond.params, cond.role))
            if price is None or ind_val is None:
                return False
            return price > ind_val if cond.op == ">" else price < ind_val

        if cond.type == "indicator_vs_indicator":
            # Two indicators compared to EACH OTHER (e.g. "EMA20 above
            # EMA50" -- MA alignment/cross), as opposed to indicator_compare
            # (indicator vs. a fixed number) or price_compare (price vs. an
            # indicator). Both sides read from the SAME role -- a strategy
            # saying "Trend (1H): 20 EMA above 50 EMA" means both EMAs are
            # the 1H versions of themselves, not one on 1H and one on entry.
            val1 = self._get(df, i, self._indicator_column(cond.indicator, cond.params, cond.role))
            val2 = self._get(df, i, self._indicator_column(cond.indicator2, cond.params2, cond.role))
            if val1 is None or val2 is None:
                return False
            return val1 > val2 if cond.op == ">" else val1 < val2

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
            #
            # Bug fix: these zone columns are forward-filled from the last
            # CONFIRMED structural level, which can be stale by the time a
            # later bar triggers a new entry -- e.g. an old bullish FVG/OB
            # low that price has since moved below, leaving it ABOVE the
            # new entry price. A "stop-loss" on the wrong side of entry
            # (above entry for a long, below entry for a short) means
            # _check_forced_exit() triggers "stop_loss" on a price move
            # that's actually favorable, mislabeling a chunk of wins as
            # losses -- confirmed against real trade data: 98% of one
            # coin's stop_loss values were on the wrong side of entry, and
            # 78% of its "stop_loss" exits were secretly profitable. Each
            # candidate is now checked against `price` and skipped (falling
            # through to the next one) if it's on the wrong side.
            if direction == "bullish":
                for col in ("entry_bull_ob_low", "entry_fvg_bull_low", "entry_support"):
                    zone = self._get(df, i, col)
                    if zone is not None and zone < price:
                        return zone
            else:
                for col in ("entry_bear_ob_high", "entry_fvg_bear_high", "entry_resistance"):
                    zone = self._get(df, i, col)
                    if zone is not None and zone > price:
                        return zone
            return None
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
        if spec.type == "structure":
            # "structure" was a documented, validator/AI-advertised SL-TP
            # type (StrategyConfig/SLTPSpec's own docstring: "below/above
            # last swing, order block, or FVG") but this branch never
            # existed -- every strategy saved with take_profit.type ==
            # "structure" got NO take-profit at all, silently, forever.
            # Confirmed directly against real trade data: 183/183 trades in
            # a real "Liquidity Sweeps" batch had take_profit == NULL in the
            # database; with no take-profit and no exit_conditions, every
            # trade could only end in a stop-loss (a loss by construction)
            # or ride to the forced end-of-data close -- explaining
            # nearly-0% win rates on every strategy that used this SL/TP
            # type (also found on "5-minute crypto scalping strategy" and
            # "PDH-PDL Signal Candle Strategy").
            #
            # Target is the OPPOSING structural zone -- the "draw on
            # liquidity" on the other side of the trade -- using the same
            # candidate priority as the stop-loss structure branch (order
            # block, then FVG, then plain support/resistance) but the zone
            # on the favorable side of price instead of the protective one.
            if direction == "bullish":
                for col in ("entry_bear_ob_high", "entry_fvg_bear_high", "entry_resistance"):
                    zone = self._get(df, i, col)
                    if zone is not None and zone > price:
                        return zone
            else:
                for col in ("entry_bull_ob_low", "entry_fvg_bull_low", "entry_support"):
                    zone = self._get(df, i, col)
                    if zone is not None and zone < price:
                        return zone
            return None
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
            elif c.type == "indicator_vs_indicator":
                p1 = c.params.get("period")
                p2 = c.params2.get("period")
                parts.append(f"{c.indicator}{p1 or ''} {c.op} {c.indicator2}{p2 or ''}")
            elif c.type == "session":
                parts.append(f"session={c.name}")
            elif c.type == "trend":
                parts.append(f"trend={c.direction}")
            else:
                parts.append(c.text or "condition")
        return " + ".join(parts) if parts else "signal"
