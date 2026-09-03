"""Turns a parsed StrategyConfig into something engine.run_backtest can run,
without hand-writing a Strategy subclass per strategy. All indicator/concept
math comes from concepts.py; this class only wires config -> columns ->
Signal.
"""

import numpy as np
import pandas as pd

from strategies.base import Strategy, Signal
from backtest_engine import concepts

_DEFAULT_PERIOD = {"ema": 20, "sma": 20, "rsi": 14, "atr": 14}

# The umbrella name PLUS every individual candlestick pattern that
# validator.known_indicator_names() advertises as usable on its own.
# _compute_concept_columns() computes this whole family in one block, so
# declaring ANY member has to be enough to trigger it -- see the block's
# own comment for the bug this prevents.
_CANDLESTICK_PATTERN_CONCEPTS = {
    "candlestick_patterns",
    "doji_confirm", "hammer_confirm", "shooting_star_confirm",
    "morning_star", "evening_star",
}

# Dumb Money Concepts' 3 entry-timing variants (Confirmation / Blind Entry /
# Combined) all share the same untested-level detection (daily_tf support/
# resistance) and the same SL/TP mechanics -- they only differ in what
# gates the actual entry moment. Grouped here so every place that needs
# "any DMC variant" (the daily_tf role setup, the structure SL/TP candidate
# columns) stays in sync with exactly 1 set instead of 3 near-duplicate
# checks.
_DMC_VARIANTS = {"dmc_confirmation", "dmc_blind_entry", "dmc_combined"}


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
            elif name == "anchored_vwap" and "anchored_vwap" not in df.columns:
                anchor = (ind["params"].get("anchor") or "swing_low")
                df["anchored_vwap"] = concepts.anchored_vwap(df, anchor=anchor)
            elif name == "cvd" and "cvd" not in df.columns:
                df["cvd"] = concepts.cumulative_volume_delta(df)
            elif name == "macd":
                # Was declared usable (validator._KNOWN_INDICATORS,
                # _PARAMETERIZED_INDICATORS) and concepts.macd() already
                # existed, but was never wired in here at all -- same bug
                # class as the vwap fix above, confirmed by a direct
                # capability audit. fast/slow/signal default to the
                # standard 12/26/9; suffixed column names support more than
                # one macd() setting on the same role without collision.
                fast = ind["params"].get("fast", 12)
                slow = ind["params"].get("slow", 26)
                sig = ind["params"].get("signal", 9)
                suffix = f"{fast}_{slow}_{sig}"
                if f"macd_line_{suffix}" not in df.columns:
                    macd_line, macd_signal, macd_hist = concepts.macd(df["close"], fast, slow, sig)
                    df[f"macd_line_{suffix}"] = macd_line
                    df[f"macd_signal_{suffix}"] = macd_signal
                    df[f"macd_hist_{suffix}"] = macd_hist
                    (df[f"macd_bull_signal_cross_{suffix}"],
                     df[f"macd_bear_signal_cross_{suffix}"]) = concepts.macd_signal_crossover(macd_line, macd_signal)
                    (df[f"macd_bull_zero_cross_{suffix}"],
                     df[f"macd_bear_zero_cross_{suffix}"]) = concepts.macd_zero_crossover(macd_line)
            elif name == "highest_high" and f"highest_high_{period}" not in df.columns:
                df[f"highest_high_{period}"] = concepts.rolling_high(df["high"], period)
            elif name == "lowest_low" and f"lowest_low_{period}" not in df.columns:
                df[f"lowest_low_{period}"] = concepts.rolling_low(df["low"], period)

        entry_df = ctx.frames.get("entry")
        if entry_df is not None and not entry_df.empty:
            used = set(self.config.concepts_used)
            self._compute_concept_columns(entry_df, used, zone_params=self.config.zone_params)
            if self.config.session_filter:
                entry_df["session"] = concepts.session_column(entry_df)
            if self.config.trend_filter:
                entry_df["trend_dir"] = concepts.trend_filter(entry_df)
            if self.config.day_filter:
                entry_df["day_of_week"] = concepts.day_of_week_column(entry_df)
            if "htf_ltf_fvg_ob_confluence" in used:
                # New Batch 3, Strategy 3: the LTF (15m) side of the
                # "HTF and LTF trend direction must match" hard filter --
                # same trend_regime() computation as the bias role gets in
                # prepare_context() above, just on the entry frame instead.
                entry_df["trend_regime"] = concepts.trend_regime(entry_df)
            if self.config.stop_loss.type == "atr_multiple" or self.config.take_profit.type == "atr_multiple":
                # Configurable ATR period (SLTPSpec.atr_period, None -> the
                # original hardcoded 14) -- see its docstring.
                periods_needed = set()
                if self.config.stop_loss.type == "atr_multiple":
                    periods_needed.add(self.config.stop_loss.atr_period or 14)
                if self.config.take_profit.type == "atr_multiple":
                    periods_needed.add(self.config.take_profit.atr_period or 14)
                for p in periods_needed:
                    col = f"atr_{p}"
                    if col not in entry_df.columns:
                        entry_df[col] = concepts.atr(entry_df, p)

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
                self._compute_concept_columns(role_df, used, zone_params=self.config.zone_params)

            if _DMC_VARIANTS & used:
                # Dumb Money Concepts' level structure is read post-merge in
                # prepare() (it needs the entry timeframe's OWN bars checked
                # against the higher-timeframe level, which only exist
                # together on one frame after ctx.build()'s merge) rather
                # than via a role-tagged Condition -- so "daily_tf" never
                # appears in _condition_roles() above and needs computing
                # here explicitly instead. Shared by all 3 DMC variants
                # (Confirmation / Blind Entry / Combined) -- they only
                # differ in entry TIMING, not in level detection.
                daily_df = ctx.frames.get("daily_tf")
                if daily_df is not None and not daily_df.empty:
                    self._compute_concept_columns(daily_df, used, zone_params=self.config.zone_params)

            if "pdhl_mtf_reversal" in used:
                # PDH/PDL Multi-Timeframe Reversal: the "15-min candle
                # CLOSES beyond PDH/PDL" confirmation must be checked on the
                # m15 role's OWN candles (a genuine 15m close, not an
                # approximation from 5m data) -- computed here, pre-merge,
                # same reasoning as _compute_role_zone_columns above.
                role_df = ctx.frames.get("m15")
                if role_df is not None and not role_df.empty:
                    if "pdh" not in role_df.columns:
                        role_df["pdh"], role_df["pdl"] = concepts.previous_day_high_low(role_df)
                    close = role_df["close"]
                    role_df["pdhl_m15_bull_confirm_event"] = (
                        (close > role_df["pdh"]) & ~(close.shift(1) > role_df["pdh"].shift(1))
                    ).fillna(False)
                    role_df["pdhl_m15_bear_confirm_event"] = (
                        (close < role_df["pdl"]) & ~(close.shift(1) < role_df["pdl"].shift(1))
                    ).fillna(False)

            if "fractal_sweep_reversal" in used:
                # 4H Fractal Sweep Reversal: needs swing-based support/
                # resistance ("fractal" levels) on the 4H role's OWN frame
                # -- support_resistance()'s ffill() already IS the "retire
                # the old level once a new 4H swing forms" rule for free
                # (a fresh confirmed swing simply replaces the forward-
                # filled value), so no separate invalidation state machine
                # is needed, unlike CRT 2.0's sweep_invalidation_state.
                role_df = ctx.frames.get("h4")
                if role_df is not None and not role_df.empty and "support" not in role_df.columns:
                    role_df["support"], role_df["resistance"] = concepts.support_resistance(role_df)

            if "cisd_entry" in used:
                # SAR + SMC (CISD Entry): needs Demand/Supply zones on the
                # 1H role's OWN frame, pre-merge -- same reasoning as
                # pdhl_mtf_reversal's m15 block above. The rest of the CISD
                # sequence (sharp move -> CISD level -> confirm -> retrace)
                # is computed post-merge in prepare() since it combines this
                # h1 zone with entry-frame price action.
                role_df = ctx.frames.get("h1")
                if role_df is not None and not role_df.empty:
                    if "demand_low" not in role_df.columns:
                        (role_df["demand_low"], role_df["demand_high"],
                         role_df["supply_low"], role_df["supply_high"]) = concepts.consolidation_impulse_zones(
                            role_df, **self.config.zone_params)

            if "htf_key_level_engulfing" in used:
                # HTF Key Level Engulfing Reversal: needs OB/FVG/liquidity-
                # sweep zones on BOTH the h1 and m15 roles (the strategy's
                # own "1H or 15M" key-level rule) -- see
                # _compute_role_zone_columns() docstring for why this can't
                # just go through the normal per-role Condition loop above.
                for role in ("h1", "m15"):
                    role_df = ctx.frames.get(role)
                    if role_df is not None and not role_df.empty:
                        self._compute_role_zone_columns(role_df)

            _LIQUIDITY_BATCH = {
                "liquidity_sweep_multi_confirm", "liquidity_sweep_cisd_swing", "ote_liquidity_sweep_reversal",
            }
            if _LIQUIDITY_BATCH & used:
                # Liquidity Sweep batch (3 new strategies, all share a
                # "bias" HTF role): pre-merge swing S/R + sweep detection on
                # the bias role's OWN frame, same reasoning as
                # fractal_sweep_reversal's h4 block above -- a bias-role
                # sweep/trend event must be computed on that role's real
                # candles before ctx.build() causally merges it onto entry.
                role_df = ctx.frames.get("bias")
                if role_df is not None and not role_df.empty:
                    if "support" not in role_df.columns:
                        role_df["support"], role_df["resistance"] = concepts.support_resistance(role_df)
                    if "liquidity_sweep_multi_confirm" in used:
                        # Strategy 1: "HTF candle must close back inside the
                        # level (confirming the sweep) BEFORE looking for
                        # entry-TF signals" -- the sweep AND its reclaim both
                        # checked on the bias role's own bars, via
                        # level_sweep_reclaim()'s exact formula +
                        # sequential_event() for genuine ordering, exactly
                        # like fractal_sweep_reversal's already-established
                        # sweep-then-reclaim composition (just entirely on
                        # the HTF frame here instead of straddling HTF-level/
                        # entry-TF-event). max_gap=5 (HTF bars): own default,
                        # a "quick" close-back per the strategy's own wording,
                        # source gives no exact number.
                        bull_sweep, bear_sweep, bull_reclaim, bear_reclaim = concepts.level_sweep_reclaim(role_df)
                        role_df["sweep_confirmed_bull"] = concepts.sequential_event(bull_sweep, bull_reclaim, max_gap=5)
                        role_df["sweep_confirmed_bear"] = concepts.sequential_event(bear_sweep, bear_reclaim, max_gap=5)
                    if "liquidity_sweep_cisd_swing" in used and "bull_liquidity_sweep" not in role_df.columns:
                        # Strategy 2: "break past one level and quickly
                        # close back inside it (sweep)" -- same-bar wick-
                        # beyond + close-back, exactly what liquidity_sweep()
                        # already checks (pure swing S/R anchor, no zones/OB,
                        # matching the strategy's own "pure swing" wording).
                        role_df["bull_liquidity_sweep"], role_df["bear_liquidity_sweep"] = concepts.liquidity_sweep(role_df)
                    if "ote_liquidity_sweep_reversal" in used and "structure_trend" not in role_df.columns:
                        # Strategy 3: "confirm HTF trend" -- reuses the same
                        # stricter trend engine mss_reversal already uses
                        # (valid_structure_trend, not the simpler same-window
                        # change_of_character), on the bias role's own bars.
                        role_df["structure_trend"] = concepts.valid_structure_trend(role_df)

            _SWEEP_ENGULF_VARIANTS = {"liquidity_sweep_engulfing_loose", "liquidity_sweep_engulfing_strict"}
            if _SWEEP_ENGULF_VARIANTS & used:
                # New Batch 5, Strategy 1 (Liquidity Sweep + Engulfing
                # Candle): "price sweeps a 4H swing low/high" needs a real
                # 4H swing level, computed on the bias role's OWN bars --
                # same reasoning as fractal_sweep_reversal's/the Liquidity
                # Sweep batch's own bias-role blocks above. The sweep EVENT
                # itself (5m price vs this 4H level) and the engulfing
                # pattern are both evaluated post-merge in prepare(),
                # against the entry frame's own low/high/close, matching
                # the source's literal "sweeps a 4H swing low ON THE 5M
                # CHART" wording.
                role_df = ctx.frames.get("bias")
                if role_df is not None and not role_df.empty and "support" not in role_df.columns:
                    role_df["support"], role_df["resistance"] = concepts.support_resistance(role_df)

            if "range_breakout_volume_confirm" in used:
                # New Batch 3, Strategy 2: the source names "Bias TF: 1H"
                # but gives no explicit mechanical trend-gate rule for it
                # (unlike Strategies 1 and 3, which both spell out exactly
                # how their HTF role gates entries) -- this strategy's own
                # entry rules (range/breakout/volume/retest) are entirely
                # self-contained on the 15m entry frame. Flagged own
                # decision: rather than inventing an unstated directional
                # filter, the declared 1H bias role is used for real
                # higher-timeframe support/resistance context in the
                # take-profit/stop-loss structural fallback chain
                # (bias_support/bias_resistance -- already wired into both
                # priority lists, e.g. ote_liquidity_sweep_reversal's own
                # "bias" role above), consistent with how every other
                # multi-role strategy in this codebase treats an HTF role
                # that isn't used for a hard gate.
                bias_df = ctx.frames.get("bias")
                if bias_df is not None and not bias_df.empty and "support" not in bias_df.columns:
                    bias_df["support"], bias_df["resistance"] = concepts.support_resistance(bias_df)

            if "trendline_breakout" in used:
                # New Batch 3, Strategy 1 (HTF Trend Trendline Breakout):
                # "trend must be confirmed on BOTH 4H and 1H" -- computed on
                # each role's OWN native-resolution bars (same reasoning as
                # fractal_sweep_reversal's h4 block above), using the SAME
                # stricter valid_structure_trend() state machine
                # mss_reversal/ote_liquidity_sweep_reversal already use for
                # "confirm HTF trend", not the simpler change_of_character.
                # trend_regime (3-way up/down/sideways) is ALSO computed on
                # the h1 role here -- a deliberately DIFFERENT, complementary
                # signal from structure_trend's sticky macro state, used only
                # by this strategy's own soft "reduce size while the 1H looks
                # ranging" filter in prepare() below (see trend_regime()'s
                # own docstring for why the two can disagree at the same bar
                # -- structure_trend can still read "up" during a pullback
                # trend_regime correctly calls "sideways").
                for role in ("h4", "h1"):
                    role_df = ctx.frames.get(role)
                    if role_df is not None and not role_df.empty and "structure_trend" not in role_df.columns:
                        role_df["structure_trend"] = concepts.valid_structure_trend(role_df)
                h1_df = ctx.frames.get("h1")
                if h1_df is not None and not h1_df.empty and "trend_regime" not in h1_df.columns:
                    h1_df["trend_regime"] = concepts.trend_regime(h1_df)

            if "htf_ltf_fvg_ob_confluence" in used:
                # New Batch 3, Strategy 3 (HTF-LTF FVG/OB Confluence Entry):
                # "mark Support/Resistance, Order Blocks, and FVGs on 4H" --
                # all three on the bias (4H) role's OWN bars, reusing
                # _compute_role_zone_columns exactly as htf_key_level_
                # engulfing already does for its own two non-entry roles.
                # order_block_validity() (OB mitigation -- "if price moves
                # past a marked Order Block before an entry occurs, that OB
                # becomes invalid") and trend_regime() (this strategy's own
                # hard "HTF sideways -> don't trade" filter, and the "HTF/LTF
                # trend must match" filter) computed here too, all on the
                # bias role's own native bars.
                bias_df = ctx.frames.get("bias")
                if bias_df is not None and not bias_df.empty:
                    self._compute_role_zone_columns(bias_df)
                    if "support" not in bias_df.columns:
                        bias_df["support"], bias_df["resistance"] = concepts.support_resistance(bias_df)
                    if "trend_regime" not in bias_df.columns:
                        bias_df["trend_regime"] = concepts.trend_regime(bias_df)
                    bias_df["bull_ob_valid"], bias_df["bear_ob_valid"] = concepts.order_block_validity(bias_df)

            if "heikin_ashi_reversal" in used:
                # New Batch 4, Strategy 1 (Heikin Ashi Trend Reversal): the
                # HA flip/strength/ranging signal is computed on the BIAS
                # (1H) role's OWN candles -- own default, since the source
                # names "1H bias, 15m entry" but doesn't spell out exactly
                # which TF the flip itself fires on; a reversal is naturally
                # a higher-timeframe trend-change event, with the 15m entry
                # role used only for the "wait for price to return"
                # precision-timing retracement -- same bias/entry role split
                # every other strategy in this codebase already uses. Short
                # side is a builder's own mirrored default (source only
                # detailed the long case explicitly).
                bias_df = ctx.frames.get("bias")
                if bias_df is not None and not bias_df.empty:
                    ha_open, ha_high, ha_low, ha_close = concepts.heikin_ashi(bias_df)
                    green = ha_close > ha_open
                    red = ha_close < ha_open
                    bull_flip = (green & red.shift(1).fillna(False)).fillna(False)
                    bear_flip = (red & green.shift(1).fillna(False)).fillna(False)
                    body = (ha_close - ha_open).abs()
                    avg_body = body.rolling(5).mean().shift(1)
                    size_increasing = (body > avg_body).fillna(False)
                    # Sideways/ranging proxy: 3+ color flips within the last
                    # 10 HA candles -- own default, source gives no exact
                    # number for "HA color has flipped frequently."
                    any_flip = (bull_flip | bear_flip)
                    is_ranging = (any_flip.rolling(10).sum() >= 3).fillna(False)
                    bull_reversal = (bull_flip & size_increasing & ~is_ranging).fillna(False)
                    bear_reversal = (bear_flip & size_increasing & ~is_ranging).fillna(False)
                    # The reversal candle's own zone (ha_low/ha_high AT the
                    # flip bar), held constant until the next opposite flip
                    # -- same ffill "active zone" pattern order_blocks()/
                    # fvg_zone() already use.
                    bias_df["ha_zone_low"] = ha_low.where(bull_reversal).ffill()
                    bias_df["ha_zone_high"] = ha_high.where(bull_reversal).ffill()
                    bias_df["ha_bear_zone_low"] = ha_low.where(bear_reversal).ffill()
                    bias_df["ha_bear_zone_high"] = ha_high.where(bear_reversal).ffill()
                    if "atr_14" not in bias_df.columns:
                        bias_df["atr_14"] = concepts.atr(bias_df, 14)
                    if "support" not in bias_df.columns:
                        bias_df["support"], bias_df["resistance"] = concepts.support_resistance(bias_df)

            if "fibonacci_golden_zone" in used:
                # New Batch 4, Strategy 2 (Fibonacci Golden Zone
                # Retracement): single-timeframe (1H = both bias and entry
                # per the source), computed directly on the entry frame --
                # nothing to do here pre-merge, see _compute_concept_columns
                # (fib levels) and prepare() (trend gate + invalidation).
                pass

            if "frvp_poc_reversal" in used:
                # New Batch 4, Strategy 3 (FRVP POC Reversal): also single-
                # timeframe (1H) per the source's own "24-hour session
                # volume profile" note -- entirely self-contained on the
                # entry frame, see _compute_concept_columns.
                pass

            if "fvg_equilibrium_entry" in used:
                # New Batch 4, Strategy 4 (FVG 50% Equilibrium Entry):
                # single-timeframe (1H) -- entirely self-contained on the
                # entry frame, see _compute_concept_columns/prepare().
                pass

            if "donchian_lwti_volume_confluence" in used:
                # New Batch 4, Strategy 5 (Donchian/LWTI/Volume Confluence):
                # Donchian breakout direction is a BIAS(1H)-role structural
                # gate ("previously flat band starts moving") while
                # LWTI/Volume confirmation fires on the entry (15m) role --
                # same bias/entry split as trendline_breakout/htf_ltf_fvg_
                # ob_confluence above. Donchian itself needs only rolling
                # high/low on the bias role's own bars.
                bias_df = ctx.frames.get("bias")
                if bias_df is not None and not bias_df.empty:
                    bias_df["donchian_high"] = concepts.rolling_high(bias_df["high"], 96)
                    bias_df["donchian_low"] = concepts.rolling_low(bias_df["low"], 96)
                    bias_df["donchian_mid"] = (bias_df["donchian_high"] + bias_df["donchian_low"]) / 2.0
                    if "support" not in bias_df.columns:
                        bias_df["support"], bias_df["resistance"] = concepts.support_resistance(bias_df)
                    # Breakout/breakdown: "a previously flat band starts
                    # moving" -- own default for "flat": the band's own
                    # high/low held unchanged for at least 8 of the last 10
                    # bars (source gives no exact number), then THIS bar
                    # makes a genuinely new 96-bar high/low.
                    band_static = ((bias_df["donchian_high"] == bias_df["donchian_high"].shift(1)) &
                                    (bias_df["donchian_low"] == bias_df["donchian_low"].shift(1)))
                    was_flat = (band_static.shift(1).rolling(10).sum() >= 8).fillna(False)
                    new_high = (bias_df["donchian_high"] > bias_df["donchian_high"].shift(1)).fillna(False)
                    new_low = (bias_df["donchian_low"] < bias_df["donchian_low"].shift(1)).fillna(False)
                    bias_df["donchian_bull_break"] = (new_high & was_flat).fillna(False)
                    bias_df["donchian_bear_break"] = (new_low & was_flat).fillna(False)

        return ctx.build()

    def _condition_roles(self):
        roles = set()
        buckets = [
            self.config.entry_conditions, self.config.exit_conditions, self.config.confirmation_conditions,
            self.config.long_entry_conditions, self.config.short_entry_conditions,
        ]
        buckets += [g.get("conditions") or [] for g in self.config.entry_rule_groups]
        for bucket in buckets:
            for cond in bucket:
                if cond.type == "concept" and cond.role:
                    roles.add(cond.role)
        return roles

    @staticmethod
    def _compute_concept_columns(df, used, zone_params=None):
        """Computes every concept-derived column `used` calls for, directly
        on `df` -- shared by the entry timeframe (always) and any other role
        a condition explicitly references (see prepare_context).

        zone_params: optional dict of consolidation_impulse_zones() overrides
        (consolidation_bars/tightness_mult/impulse_atr_mult/atr_period) --
        lets a strategy tune what counts as "tight"/"sharp" for its own
        demand_zone/supply_zone, since the source document for this kind of
        strategy typically gives no exact number for either. None/empty
        uses the function's own defaults, unchanged for every strategy that
        doesn't set this."""
        zone_params = zone_params or {}
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
        if "order_block_reversal" in used:
            # Order Block Reversal strategy: same shape as fvg_reversal
            # above (this session's other new Concepts-Library-to-strategy
            # build) -- reaction-on-retest via candle_pattern_confirmation()
            # reused directly, once-per-zone freshness via
            # first_signal_per_level() reused directly. The one genuinely
            # NEW element the Concepts Library's own Order Block entry
            # requires that fvg_reversal didn't: a LOCATION filter (an OB
            # "near a higher-timeframe support/resistance... is stronger"
            # is written into that entry's own golden_rule as a real AND
            # condition, not just a descriptive aside) -- represented via
            # the same ATR-scaled proximity band already built for DMC
            # Combined's zone-buffer (concepts.within_level_zone's sibling
            # idea, done inline here since within_level_zone itself checks
            # against df["close"], not an arbitrary zone bound), own-default
            # 0.5x ATR(14), flagged as a builder default since the source
            # material gives no exact "near" distance.
            if "bull_ob_low" not in df.columns:
                bl, bh, brl, brh = concepts.order_blocks(df)
                df["bull_ob_low"], df["bull_ob_high"] = bl, bh
                df["bear_ob_low"], df["bear_ob_high"] = brl, brh
            if "support" not in df.columns:
                df["support"], df["resistance"] = concepts.support_resistance(df)
            atr14 = concepts.atr(df, 14)
            near_support = ((df["bull_ob_low"] - df["support"]).abs() <= atr14 * 0.5).fillna(False)
            near_resistance = ((df["bear_ob_high"] - df["resistance"]).abs() <= atr14 * 0.5).fillna(False)

            close = df["close"]
            bull_inside = ((close >= df["bull_ob_low"]) & (close <= df["bull_ob_high"]) & near_support).fillna(False)
            bull_tag = bull_inside & ~bull_inside.shift(1).fillna(False)
            bear_inside = ((close >= df["bear_ob_low"]) & (close <= df["bear_ob_high"]) & near_resistance).fillna(False)
            bear_tag = bear_inside & ~bear_inside.shift(1).fillna(False)
            raw_long = concepts.candle_pattern_confirmation(bull_tag, df, "bullish")
            raw_short = concepts.candle_pattern_confirmation(bear_tag, df, "bearish")
            df["ob_reversal_long_confirm"] = concepts.first_signal_per_level(raw_long, df["bull_ob_low"])
            df["ob_reversal_short_confirm"] = concepts.first_signal_per_level(raw_short, df["bear_ob_high"])
        if "eqhl_reversal" in used:
            # Equal Highs/Lows Reversal strategy: the Concepts Library's
            # own entry explicitly reuses Liquidity Sweep's sweep-then-
            # reclaim mechanics (level_sweep_reclaim()'s exact shape), just
            # anchored to an EQUAL-highs/lows level instead of a plain
            # nearest swing S/R level -- so this block is level_sweep_
            # reclaim()'s own formula, copied verbatim, with `support`/
            # `resistance` swapped for the equal-highs/lows level series.
            # No location hard-gate: the entry's golden_rule states EQH/EQL
            # + sweep + reclaim = valid setup on its own; "near a higher-
            # timeframe level" is documented as making the setup STRONGER,
            # not as a required AND condition (contrast with FVG's HTF-bias
            # gate and Order Block's location filter, both hard requirements
            # in their own golden_rule text) -- implemented literally as
            # written, not over-filtered.
            if "bull_equal_lows" not in df.columns:
                df["bull_equal_lows"], df["bear_equal_highs"] = concepts.equal_highs_lows(df)
            df["eq_low_level"] = df["low"].where(df["bull_equal_lows"]).ffill()
            df["eq_high_level"] = df["high"].where(df["bear_equal_highs"]).ffill()
            low, high, close = df["low"], df["high"], df["close"]
            bull_sweep = (low < df["eq_low_level"]).fillna(False)
            bear_sweep = (high > df["eq_high_level"]).fillna(False)
            was_below = (close.shift(1) <= df["eq_low_level"].shift(1)).fillna(False)
            was_above = (close.shift(1) >= df["eq_high_level"].shift(1)).fillna(False)
            bull_reclaim = ((close > df["eq_low_level"]) & was_below).fillna(False)
            bear_reclaim = ((close < df["eq_high_level"]) & was_above).fillna(False)
            df["eqhl_long_confirm"] = concepts.sequential_event(bull_sweep, bull_reclaim)
            df["eqhl_short_confirm"] = concepts.sequential_event(bear_sweep, bear_reclaim)
        if "support" in used or "resistance" in used or "liquidity_sweep" in used:
            df["support"], df["resistance"] = concepts.support_resistance(df)
        if "liquidity_sweep" in used:
            df["bull_liquidity_sweep"], df["bear_liquidity_sweep"] = concepts.liquidity_sweep(df)
        if "sweep_invalidation_state" in used:
            # CRT 2.0's invalidation rule ("sweeps the bottom and closes
            # inside, but then sweeps the top and closes inside before
            # entry -> setup invalid"): must run AFTER the liquidity_sweep
            # block above, which computes the bull/bear_liquidity_sweep
            # columns this reads.
            df["long_setup_active"], df["short_setup_active"] = concepts.sweep_invalidation_state(
                df["bull_liquidity_sweep"], df["bear_liquidity_sweep"])
        if "double_choch_confirmation" in used:
            # CHoCH-with-Liquidity-Trap's strict event order (must run
            # AFTER the "choch"/"liquidity_sweep" blocks above, which
            # compute the bull_choch/bear_choch and bull_liquidity_sweep/
            # bear_liquidity_sweep columns this reads): an initial CHoCH
            # ("wake-up call"), THEN a retest/sweep strictly after it, THEN
            # a SECOND CHoCH strictly after that retest -- two chained
            # concepts.sequential_event() calls, reusing the same generic
            # ordering primitive twice instead of a bespoke 3-stage
            # function. The second call's event_b is bull_choch/bear_choch
            # again, but sequential_event's strict "b's bar > a's bar"
            # requirement means it can only match a CHoCH occurrence
            # genuinely later than the retest bar -- a real second/different
            # formation, not the same original event re-counted.
            retest_after_initial_bull = concepts.sequential_event(df["bull_choch"], df["bull_liquidity_sweep"])
            df["bull_double_choch"] = concepts.sequential_event(retest_after_initial_bull, df["bull_choch"])
            retest_after_initial_bear = concepts.sequential_event(df["bear_choch"], df["bear_liquidity_sweep"])
            df["bear_double_choch"] = concepts.sequential_event(retest_after_initial_bear, df["bear_choch"])
        if "candle_break" in used:
            df["bull_candle_break"], df["bear_candle_break"] = concepts.candle_break(df)
        if "trendline_breakout" in used:
            # New Batch 3, Strategy 1: computed on WHATEVER frame this runs
            # on -- for this strategy that's always the entry (15m) role,
            # since the trendline itself is drawn from entry-TF swing
            # points (the "range/pullback" the strategy describes happens
            # on entry TF, not the HTF bias roles).
            df["bull_trendline_break"], df["bear_trendline_break"] = concepts.trendline_breakout(df)
            # Dedicated, LARGER-lookback swing series for the structural
            # trailing stop (see engine._update_trailing_stop) -- measured
            # bug, not a style choice: reusing the plain "support"/
            # "resistance" columns (lookback=2, tuned for a sensitive ENTRY
            # trigger) as the trailing basis trailed the stop up to a fresh
            # micro-pivot almost every bar, stopping every single trade out
            # within 1-2 bars at under 1R (confirmed on a real 240-day
            # BTCUSDT smoke test: 765 trades, max R achieved across ALL of
            # them was 0.95). lookback=8 -- own default, a genuinely
            # larger/more significant swing basis a trend-following trail
            # needs room to run against, still using the exact same
            # support_resistance() primitive, just a different window.
            # engine.py prefers these "entry_trail_*" columns over the
            # plain entry_support/entry_resistance ones when both exist,
            # falling back to the plain ones for any OTHER strategy that
            # sets trailing_stop={"type":"structure"} without providing its
            # own dedicated trail columns -- so the mechanism itself stays
            # genuinely general/reusable, not special-cased to this one
            # strategy.
            df["trail_support"], df["trail_resistance"] = concepts.support_resistance(df, lookback=8)
        if "range_breakout_volume_confirm" in used:
            # New Batch 3, Strategy 2: entirely self-contained on the entry
            # (15m) frame -- range detection, the breakout candle, its
            # volume spike, and the standard/retest branching are all
            # explicitly described on entry TF in the strategy's own rules.
            (df["range_vol_bull_confirm"], df["range_vol_bear_confirm"],
             df["range_vol_sl_bull"], df["range_vol_sl_bear"]) = concepts.range_breakout_volume_confirm(df)
        if "fibonacci_golden_zone" in used:
            # New Batch 4, Strategy 2 (Fibonacci Golden Zone Retracement):
            # single-timeframe (1H, per the source), entirely self-contained
            # here -- no post-merge step needed. Long: uptrend leg, price
            # retraces into the 50%-61.8% zone. Short: downtrend leg, price
            # retraces into the 61.8% zone specifically (per the source's
            # own asymmetric wording) -- represented as the same [fib_50,
            # fib_618] band check as the long side (fibonacci_retracement_
            # zone()'s own docstring explains why fib_50/fib_618 sit in
            # mirrored order for a down leg), since 61.8% is the outer edge
            # of that same golden-zone band either way.
            fib_618, fib_50, fib_382, direction = concepts.fibonacci_retracement_zone(df)
            df["fib_618"], df["fib_50"], df["fib_382"], df["fib_direction"] = fib_618, fib_50, fib_382, direction
            close = df["close"]
            is_up = (direction == "up")
            is_down = (direction == "down")
            in_zone_up = (is_up & (close >= fib_618) & (close <= fib_50)).fillna(False)
            in_zone_down = (is_down & (close >= fib_50) & (close <= fib_618)).fillna(False)
            # Invalidation: "if price breaks past the 61.8% level against
            # the trade direction, the setup is invalid" -- a state that
            # persists until a genuinely NEW leg forms, via the same
            # groupby+cummax "state resets when the zone identity changes"
            # shape order_block_validity() already uses (leg_id increments
            # whenever fib_618's own value changes, i.e. exactly when a new
            # leg confirms).
            leg_changed = (fib_618 != fib_618.shift(1)).fillna(True)
            leg_id = leg_changed.cumsum()
            invalid_now_up = (is_up & (close < fib_618)).fillna(False)
            invalid_now_down = (is_down & (close > fib_618)).fillna(False)
            invalidated_up = invalid_now_up.groupby(leg_id).cummax()
            invalidated_down = invalid_now_down.groupby(leg_id).cummax()
            tag_up = (in_zone_up & ~in_zone_up.shift(1).fillna(False) & ~invalidated_up.shift(1).fillna(False))
            tag_down = (in_zone_down & ~in_zone_down.shift(1).fillna(False) & ~invalidated_down.shift(1).fillna(False))
            df["fib_long_confirm"] = concepts.first_signal_per_level(tag_up.fillna(False), fib_618)
            df["fib_short_confirm"] = concepts.first_signal_per_level(tag_down.fillna(False), fib_618)
            # SL: "slightly beyond the 61.8% level" -- fed into
            # _compute_stop_loss()'s structure candidate chain.
            df["fib_sl_bull"] = fib_618.where(is_up)
            df["fib_sl_bear"] = fib_618.where(is_down)
        if "frvp_poc_reversal" in used:
            # New Batch 4, Strategy 3 (FRVP POC Reversal): single-timeframe
            # (1H, per the source's own "24-hour session volume profile"
            # crypto-specific note). REQUIRED additional filter ("do not
            # trade FRVP in isolation"): a confirming candle pattern
            # (Engulfing OR Hammer/pin_bar, both existing concepts, reused
            # directly) must fire on the SAME bar as the POC-zone touch --
            # a hard AND, not a scoring bonus.
            poc, frvp_direction = concepts.fixed_range_volume_profile(df)
            df["frvp_poc"], df["frvp_direction"] = poc, frvp_direction
            if "atr_14" not in df.columns:
                df["atr_14"] = concepts.atr(df, 14)
            atr14 = df["atr_14"]
            buffer = 0.5 * atr14
            poc_low, poc_high = poc - buffer, poc + buffer
            close, low, high = df["close"], df["low"], df["high"]
            in_zone = ((low <= poc_high) & (high >= poc_low)).fillna(False)
            was_above = (close.shift(1) > poc_high.shift(1)).fillna(False)
            was_below = (close.shift(1) < poc_low.shift(1)).fillna(False)
            tag_from_above = (in_zone & was_above).fillna(False)
            tag_from_below = (in_zone & was_below).fillna(False)
            # "Also allow an immediate short entry on a clean breakdown
            # through a POC that was acting as support" -- source's own
            # explicit extra entry mode, still subject to the same
            # candle-pattern hard filter below.
            breakdown = ((close < poc_low) & (close.shift(1) >= poc_low.shift(1))).fillna(False)

            if "bull_engulfing" not in df.columns:
                df["bull_engulfing"], df["bear_engulfing"] = concepts.engulfing_candle(df)
            if "bull_pin_bar" not in df.columns:
                df["bull_pin_bar"], df["bear_pin_bar"] = concepts.pin_bar(df)
            bull_pattern = (df["bull_engulfing"] | df["bull_pin_bar"]).fillna(False)
            bear_pattern = (df["bear_engulfing"] | df["bear_pin_bar"]).fillna(False)

            df["frvp_long_confirm"] = (tag_from_above & bull_pattern).fillna(False)
            df["frvp_short_confirm"] = ((tag_from_below | breakdown) & bear_pattern).fillna(False)
            # SL: "slightly beyond the POC zone."
            df["frvp_sl_bull"] = poc_low
            df["frvp_sl_bear"] = poc_high

        _frvp_shape_used = {"frvp_hvn_reaction", "frvp_lvn_breakout"} & used
        if _frvp_shape_used:
            # New Batch 5, Strategy 2 (Fixed Range Volume Profile, Market
            # Shape Classification): single-timeframe (1H) per the source's
            # own "24-hour session volume profile" crypto convention, same
            # as the existing frvp_poc_reversal strategy above -- entirely
            # self-contained on the entry frame (this runs on the entry
            # role's OWN pre-merge frame, exactly like frvp_poc_reversal's
            # block above -- the "entry_" prefix these columns end up under
            # is applied later by MultiTimeframeContext.build(), not here).
            # See concepts.frvp_market_shape()'s own docstring for the
            # shape/HVN/LVN construction and every builder default it
            # documents.
            (poc, vah, val, mshape, hvn_lo_lo, hvn_lo_hi, hvn_hi_lo, hvn_hi_hi,
             lvn_lo, lvn_hi, p_invalid) = concepts.frvp_market_shape(df)
            df["frvp2_poc"], df["frvp2_vah"], df["frvp2_val"], df["frvp2_shape"] = poc, vah, val, mshape
            df["frvp2_hvn_lo_lo"], df["frvp2_hvn_lo_hi"] = hvn_lo_lo, hvn_lo_hi
            df["frvp2_hvn_hi_lo"], df["frvp2_hvn_hi_hi"] = hvn_hi_lo, hvn_hi_hi
            df["frvp2_lvn_lo"], df["frvp2_lvn_hi"] = lvn_lo, lvn_hi

            # "LONG entry (HVN/Support): in bullish P-shape or bottom of
            # D-shape, price respects HVN as support" / "SHORT entry (HVN/
            # Resistance): in bearish b-shape or top of D-shape" -- D-shape
            # supports BOTH sides (its own "top of D = resistance, bottom
            # of D = support" wording), capital_b explicitly supports both
            # ("both HVNs act as separate support/resistance levels"). A
            # P-shape long is additionally invalid once price has closed
            # below the profile's 50% level during this same leg (source's
            # own explicit invalidation rule).
            shape_allows_long = mshape.isin(["p", "d", "capital_b"]) & ~((mshape == "p") & p_invalid)
            shape_allows_short = mshape.isin(["b", "d", "capital_b"])

            if "frvp_hvn_reaction" in used:
                # "Entry confirmation: wait for a liquidity sweep at the
                # high-volume level before entering" -- reaction_at_level()
                # is exactly this (wick beyond the zone's outer edge, close
                # back inside), anchored to the lower HVN zone's own low
                # edge (support) and the higher HVN zone's own high edge
                # (resistance). For p/b/d shapes (one HVN cluster) the low
                # and high zones are the SAME zone; for capital_b they are
                # the two genuinely distinct zones.
                bull_reaction, bear_reaction = concepts.reaction_at_level(df, hvn_lo_lo, hvn_hi_hi)
                df["frvp_hvn_support_long"] = (bull_reaction & shape_allows_long).fillna(False)
                df["frvp_hvn_resistance_short"] = (bear_reaction & shape_allows_short).fillna(False)
                # SL: "below/above the HVN/support (or swing low) that
                # defined the long entry" -- the zone's own outer edge.
                df["frvp2_sl_bull"] = hvn_lo_lo
                df["frvp2_sl_bear"] = hvn_hi_hi
                # TP (not specified in source -- structure-based default,
                # "next significant HVN/POC in the direction of the trade"):
                # the opposite HVN zone's edge when a genuinely separate one
                # exists (capital_b), else this leg's own Value Area High/
                # Low as the nearest "next node" fallback.
                is_capital_b = (mshape == "capital_b")
                df["frvp2_tp_bull"] = hvn_hi_hi.where(is_capital_b, vah)
                df["frvp2_tp_bear"] = hvn_lo_lo.where(is_capital_b, val)

            if "frvp_lvn_breakout" in used:
                # "LONG entry (LVN Breakout): price enters an LVN area from
                # below" / mirror short -- edge-triggered crossing into the
                # zone, not plain containment (a fresh arrival event, same
                # reasoning as fvg_zone's edge-triggered re-entry above).
                close = df["close"]
                bull_break = ((close > lvn_lo) & ~(close.shift(1) > lvn_lo.shift(1))).fillna(False)
                bear_break = ((close < lvn_hi) & ~(close.shift(1) < lvn_hi.shift(1))).fillna(False)
                # Filter: "avoid high-conviction fast-move trades inside an
                # HVN zone itself -- only trade LVN breakouts for the fast
                # move entries, not inside HVN zones."
                in_any_hvn = (((close >= hvn_lo_lo) & (close <= hvn_lo_hi)) |
                              ((close >= hvn_hi_lo) & (close <= hvn_hi_hi))).fillna(False)
                df["frvp_lvn_breakout_long"] = (bull_break & ~in_any_hvn).fillna(False)
                df["frvp_lvn_breakout_short"] = (bear_break & ~in_any_hvn).fillna(False)
                if "frvp2_sl_bull" not in df.columns:
                    df["frvp2_sl_bull"] = hvn_lo_lo
                    df["frvp2_sl_bear"] = hvn_hi_hi
                    is_capital_b = (mshape == "capital_b")
                    df["frvp2_tp_bull"] = hvn_hi_hi.where(is_capital_b, vah)
                    df["frvp2_tp_bear"] = hvn_lo_lo.where(is_capital_b, val)

        if "sr_liquidity_sweep_sideways" in used:
            # New Batch 5, Strategy 3 (Support/Resistance + Liquidity
            # Sweep, Sideways Market): single timeframe (1H per the
            # source), entirely self-contained on the entry role's own
            # frame -- same reasoning as frvp_poc_reversal/frvp_market_shape
            # above. "S/R = a level reacted to at least twice" -- approximated
            # by the same swing-based support_resistance() every other
            # strategy in this codebase already uses as its S/R anchor.
            if "support" not in df.columns:
                df["support"], df["resistance"] = concepts.support_resistance(df)
            support, resistance = df["support"], df["resistance"]
            bull_long_wick, bear_long_wick = concepts.long_wick_candle(df)
            low, high, close = df["low"], df["high"], df["close"]
            touch_support = (low <= support).fillna(False)
            touch_resistance = (high >= resistance).fillna(False)
            # "Wait for price to enter the zone for the 3rd or 4th time" --
            # concepts.nth_touch_of_level(), own default n=3 ("3rd or 4th"
            # reads as "at least a few tests", not one exact count).
            support_tested = concepts.nth_touch_of_level(touch_support, support, n=3)
            resistance_tested = concepts.nth_touch_of_level(touch_resistance, resistance, n=3)

            bull_setup = (touch_support & bull_long_wick & support_tested).fillna(False)
            bear_setup_raw = (touch_resistance & bear_long_wick & resistance_tested).fillna(False)
            # Filter (source point 22): "do NOT take short positions if the
            # overall market trend is strongly upward" -- own default for
            # "strongly upward": concepts.trend_regime()'s own "up" state
            # (EMA(50)+ATR(14)-based, already the project's established
            # 3-way trend/sideways default -- reused here, and again for
            # Strategy 4/7/9's own trend/sideways filters, for consistency).
            # Longs are NOT similarly filtered -- the source only states
            # this rule for shorts.
            trend = concepts.trend_regime(df)
            bear_setup = (bear_setup_raw & (trend != "up")).fillna(False)

            # Execution: "enter short on the candle immediately following
            # the long-wick candle" (source, explicit) -- own consistent
            # default applied to longs too (source's "buy slightly above
            # the support zone after the long-wick candle forms" reads the
            # same way: the confirming action happens on the NEXT candle),
            # matching Strategy 1's identical next_candle_open convention.
            df["sr_sweep_long_confirm"] = bull_setup
            df["sr_sweep_short_confirm"] = bear_setup
            # SL: "slightly below/above the low/high of the long-wick
            # candle itself" -- sparse (only non-NaN on the exact signal
            # bar), same technique as range_breakout_volume_confirm's own
            # breakout-candle SL anchor.
            df["sr_sweep_sl_bull"] = low.where(bull_setup)
            df["sr_sweep_sl_bear"] = high.where(bear_setup)
            # TP, Fixed-RR variant only (source: "1:2.5 for longs, >= 1:2
            # for shorts" -- two DIFFERENT ratios, which SLTPSpec's single
            # shared `value` cannot express for a "rr"-type spec covering
            # both directions at once). Precomputed here as real target
            # PRICES and delivered through the generic "structure"
            # take-profit candidate chain instead -- exactly the same
            # technique Sniper Headshot Entry's structure_or_rr type uses
            # for its own RR fallback, just applied per-direction. Only
            # populated when the Fixed-RR variant marker is present in
            # concepts_used; the Structure variant (recent high/low) needs
            # no extra column at all -- entry_resistance/entry_support are
            # ALREADY the generic structure take-profit fallback targets.
            if "sr_sweep_tp_fixed_rr" in used:
                risk_bull = (close - df["sr_sweep_sl_bull"]).clip(lower=0)
                risk_bear = (df["sr_sweep_sl_bear"] - close).clip(lower=0)
                df["sr_sweep_fixed_tp_bull"] = close + 2.5 * risk_bull
                df["sr_sweep_fixed_tp_bear"] = close - 2.0 * risk_bear

        if "fvg_momentum_pullback" in used:
            # New Batch 5, Strategy 4 (FVG Momentum Pullback, Trending
            # Market): single timeframe (1H, source gives no other role),
            # self-contained on the entry frame. Reuses fair_value_gap()/
            # fvg_zone() entirely -- the exact same 3-candle gap
            # construction the source itself describes ("gap between the
            # wicks of the candles immediately preceding and following the
            # momentum candle").
            if "fvg_bull_low" not in df.columns:
                (df["fvg_bull_low"], df["fvg_bull_high"],
                 df["fvg_bear_low"], df["fvg_bear_high"]) = concepts.fvg_zone(df)
            fvg_bull_low, fvg_bull_high = df["fvg_bull_low"], df["fvg_bull_high"]
            fvg_bear_low, fvg_bear_high = df["fvg_bear_low"], df["fvg_bear_high"]
            # "Momentum candle": a large green/red candle -- own default,
            # same body_pct>=50% threshold this batch already established
            # for "large/momentum candle" (fractal_sweep_reversal's own
            # "strong candle" gate), for consistency. The gap's PRODUCING
            # candle is bar i-1 relative to the gap's own confirmation bar
            # i (classic 3-candle FVG shape: candle i-2, momentum candle
            # i-1, candle i) -- so this reads candle i-1's own body_pct via
            # .shift(1).
            body = (df["open"] - df["close"]).abs()
            rng = (df["high"] - df["low"]).replace(0, np.nan)
            body_pct = (body / rng).fillna(0.0) * 100.0
            momentum_candle = (body_pct.shift(1) >= 50.0).fillna(False)

            fvg_bull_mid = (fvg_bull_low + fvg_bull_high) / 2.0
            fvg_bear_mid = (fvg_bear_low + fvg_bear_high) / 2.0
            close = df["close"]
            # "Price pulls back into the FVG and reaches/dips slightly
            # below the 50% line" -- edge-triggered cross INTO the midpoint
            # from the favorable side (a genuine pullback arrival, not
            # "is currently below it" -- same containment-vs-event
            # reasoning as fvg_zone's own edge-triggered re-entry).
            touch_mid_bull = ((close <= fvg_bull_mid) & (close.shift(1) > fvg_bull_mid.shift(1))).fillna(False)
            touch_mid_bear = ((close >= fvg_bear_mid) & (close.shift(1) < fvg_bear_mid.shift(1))).fillna(False)
            bull_raw = (touch_mid_bull & momentum_candle).fillna(False)
            bear_raw = (touch_mid_bear & momentum_candle).fillna(False)
            # Filter (source point 22, shared with Strategy 3): "do NOT
            # take short positions if the overall market trend is strongly
            # upward" -- same trend_regime() default as Strategy 3, for
            # consistency across this batch.
            trend = concepts.trend_regime(df)
            bull_confirm = concepts.first_signal_per_level(bull_raw, fvg_bull_low)
            bear_confirm = concepts.first_signal_per_level(
                (bear_raw & (trend != "up")).fillna(False), fvg_bear_high)
            df["fvgmp_long_confirm"] = bull_confirm
            df["fvgmp_short_confirm"] = bear_confirm
            # SL: "slightly below/above the FVG zone" (source, explicit) --
            # the zone's own outer edge.
            df["fvgmp_sl_bull"] = fvg_bull_low
            df["fvgmp_sl_bear"] = fvg_bear_high

        if "fvg_pure_inverse" in used:
            # New Batch 5, Strategy 5 (FVG Pure + Inverse FVG): single
            # timeframe (1H, source gives no other role), self-contained.
            # Reuses fair_value_gap()/fvg_zone() entirely -- the exact same
            # 3-candle gap the source itself describes ("2nd candle = very
            # large momentum candle, zone = high of 1st to low of 3rd").
            # "Very large" momentum candle: same body_pct>=50% threshold as
            # Strategy 4, per the task's own explicit "same as Strategy 4,
            # for consistency" instruction.
            if "fvg_bull_low" not in df.columns:
                (df["fvg_bull_low"], df["fvg_bull_high"],
                 df["fvg_bear_low"], df["fvg_bear_high"]) = concepts.fvg_zone(df)
            if "bull_fvg" not in df.columns:
                df["bull_fvg"], df["bear_fvg"] = concepts.fair_value_gap(df)
            fvg_bull_low, fvg_bull_high = df["fvg_bull_low"], df["fvg_bull_high"]
            fvg_bear_low, fvg_bear_high = df["fvg_bear_low"], df["fvg_bear_high"]
            bull_fvg_event, bear_fvg_event = df["bull_fvg"], df["bear_fvg"]

            body = (df["open"] - df["close"]).abs()
            rng = (df["high"] - df["low"]).replace(0, np.nan)
            body_pct = (body / rng).fillna(0.0) * 100.0
            momentum_candle = (body_pct.shift(1) >= 50.0).fillna(False)

            close = df["close"]
            fvg_bull_mid = (fvg_bull_low + fvg_bull_high) / 2.0
            fvg_bear_mid = (fvg_bear_low + fvg_bear_high) / 2.0

            # Base setup: "buy when price returns to the 50% midpoint or
            # slightly below it" -- edge-triggered arrival, same formula as
            # Strategy 4's own pullback entry.
            touch_mid_bull = ((close <= fvg_bull_mid) & (close.shift(1) > fvg_bull_mid.shift(1))).fillna(False)
            touch_mid_bear = ((close >= fvg_bear_mid) & (close.shift(1) < fvg_bear_mid.shift(1))).fillna(False)
            base_long_raw = (touch_mid_bull & momentum_candle).fillna(False)
            base_short_raw = (touch_mid_bear & momentum_candle).fillna(False)
            # Mitigation filter (source point 8: "do NOT trade an FVG if
            # price has already returned to touch/fill that gap
            # previously"): interpreted as "each specific FVG zone can only
            # ever trigger ONE trade, ever" -- concepts.first_signal_per_
            # level()'s existing "retire once used" mechanism IS this rule
            # (not concepts.mitigation_blocks(), which measures a
            # structurally different, BOS-triggered Order-Block-body zone,
            # unrelated to "has THIS FVG already been touched").
            base_long_confirm = concepts.first_signal_per_level(base_long_raw, fvg_bull_low)
            base_short_confirm = concepts.first_signal_per_level(base_short_raw, fvg_bear_high)

            # Inverse FVG (source point 5, genuinely new composite): a
            # Bullish FVG that gets "broken" (price CLOSES below it) flips
            # into a bearish reversal trigger -- wait for price to return
            # to that now-broken zone's own 50% level FROM BELOW, then
            # short. Mirror for a broken Bearish FVG enabling a long
            # (source only spelled out the bullish-broken-to-short case
            # explicitly; the mirror is a structural, not discretionary,
            # inference, per the task's own instruction).
            bull_broken_event = ((close < fvg_bull_low) & ~(close.shift(1) < fvg_bull_low.shift(1))).fillna(False)
            bear_broken_event = ((close > fvg_bear_high) & ~(close.shift(1) > fvg_bear_high.shift(1))).fillna(False)
            inverse_short_level = fvg_bull_mid.where(bull_broken_event).ffill()
            inverse_long_level = fvg_bear_mid.where(bear_broken_event).ffill()
            inverse_short_touch = ((close >= inverse_short_level) & (close.shift(1) < inverse_short_level.shift(1))).fillna(False)
            inverse_long_touch = ((close <= inverse_long_level) & (close.shift(1) > inverse_long_level.shift(1))).fillna(False)
            inverse_short_confirm = concepts.first_signal_per_level(inverse_short_touch, inverse_short_level)
            inverse_long_confirm = concepts.first_signal_per_level(inverse_long_touch, inverse_long_level)

            df["fvgpi_long_confirm"] = (base_long_confirm | inverse_long_confirm).fillna(False)
            df["fvgpi_short_confirm"] = (base_short_confirm | inverse_short_confirm).fillna(False)
            # SL: "slightly below/above the FVG zone" (base setup, source's
            # own wording) -- for the inverse setup, the (now-broken) zone
            # has flipped polarity (a broken bullish/support zone now acts
            # as resistance, and vice versa), so its own OTHER edge is the
            # correct protective side: an inverse LONG (from a broken
            # BEARISH zone acting as new support) stops below that zone's
            # own low; an inverse SHORT (from a broken BULLISH zone acting
            # as new resistance) stops above that zone's own high -- same
            # "structural zone's outer edge" principle as the base setup,
            # just applied to the zone that's actually active for this
            # signal.
            df["fvgpi_sl_bull"] = fvg_bull_low.where(base_long_confirm, fvg_bear_low)
            df["fvgpi_sl_bear"] = fvg_bear_high.where(base_short_confirm, fvg_bull_high)
            # TP, Fixed-RR variant only -- symmetric 1:2 both sides (source:
            # "OR fixed ratios of 1:2 or 1:3" for the base setup; this
            # batch's own Strategy 4 already covers 1:3 as a separate
            # concept, so Strategy 5's own Fixed-RR variant uses 1:2, its
            # OTHER explicitly-named ratio, to keep the two strategies'
            # fixed-RR variants distinct rather than duplicating one).
            # take_profit.type="rr" applies this directly and symmetrically
            # -- no precomputed column needed (unlike Strategy 3's
            # asymmetric long/short ratio case).

        _ob_trade_used = {"order_block_trading_loose", "order_block_trading_strict"} & used
        if _ob_trade_used:
            # New Batch 5, Strategy 6 (Order Block Trading): single
            # timeframe, self-contained on the entry frame. The source's
            # "large green/red momentum candle after a correction" trigger
            # is approximated by this codebase's own ESTABLISHED, BOS-
            # triggered Order Block definition (concepts.order_blocks()) --
            # the exact same operational definition every other Order-
            # Block strategy in this codebase already uses -- rather than
            # building a second, parallel momentum-candle-size-triggered OB
            # detector. Reused entirely, unmodified: order_blocks() (the
            # zone itself), order_block_validity() (source's own explicit
            # "do NOT trade a mitigated OB" filter), fair_value_gap()
            # (source's own explicit "do NOT trade if there's no FVG"
            # filter), liquidity_sweep() (source's own explicit "do NOT
            # trade if liquidity was already swept before the OB formed"
            # filter).
            bull_ob_low, bull_ob_high, bear_ob_low, bear_ob_high = concepts.order_blocks(df)
            bull_ob_valid, bear_ob_valid = concepts.order_block_validity(df)
            bull_fvg_event, bear_fvg_event = concepts.fair_value_gap(df)
            bull_sweep_event, bear_sweep_event = concepts.liquidity_sweep(df)

            # "Do NOT trade if there is no FVG" -- a genuine gap must have
            # accompanied THIS specific OB's formation. Held for the OB's
            # whole lifetime once found near its formation bar (own
            # default: within a 3-bar window around formation, since a BOS
            # candle and its accompanying gap don't always land on the
            # exact same bar index).
            bull_ob_formed = (bull_ob_low != bull_ob_low.shift(1)) & bull_ob_low.notna()
            bear_ob_formed = (bear_ob_high != bear_ob_high.shift(1)) & bear_ob_high.notna()
            fvg_near_bull = bull_fvg_event.rolling(3, min_periods=1).max().astype(bool)
            fvg_near_bear = bear_fvg_event.rolling(3, min_periods=1).max().astype(bool)
            has_fvg_bull = fvg_near_bull.where(bull_ob_formed).ffill().fillna(False).astype(bool)
            has_fvg_bear = fvg_near_bear.where(bear_ob_formed).ffill().fillna(False).astype(bool)

            # "Do NOT trade if liquidity was already swept in the candle
            # BEFORE the Order Block formed" -- own default: no sweep
            # event in the 3 bars immediately before formation, held for
            # the OB's whole lifetime, same technique as the FVG check
            # above.
            sweep_before_bull = bull_sweep_event.shift(1).rolling(3, min_periods=1).max().astype(bool)
            sweep_before_bear = bear_sweep_event.shift(1).rolling(3, min_periods=1).max().astype(bool)
            no_prior_sweep_bull = (~sweep_before_bull.where(bull_ob_formed).ffill().fillna(False).astype(bool))
            no_prior_sweep_bear = (~sweep_before_bear.where(bear_ob_formed).ffill().fillna(False).astype(bool))

            # "Buy limit order at the high of the OB zone, for when price
            # returns to it" -- a wick touching that exact level while the
            # OB is still valid and passes both filters above.
            low, high = df["low"], df["high"]
            touch_bull = ((low <= bull_ob_high) & (high >= bull_ob_high)).fillna(False)
            touch_bear = ((low <= bear_ob_low) & (high >= bear_ob_low)).fillna(False)
            bull_raw = (touch_bull & bull_ob_valid & has_fvg_bull & no_prior_sweep_bull).fillna(False)
            bear_raw = (touch_bear & bear_ob_valid & has_fvg_bear & no_prior_sweep_bear).fillna(False)

            if "order_block_trading_strict" in used:
                # STRICT (shared "General Filters & Confirmations"
                # checklist source): price above/below BOTH the 200 EMA
                # and 50 EMA in the trade direction. Requires the strategy
                # to have declared both as entry-role indicators (see the
                # StrategyConfig builder) -- if either is missing, the
                # strict gate simply never opens (no crash), same
                # "declared but not computed = always False" convention
                # used throughout this codebase.
                close = df["close"]
                ema200 = df.get("ema_200")
                ema50 = df.get("ema_50")
                if ema200 is not None and ema50 is not None:
                    trend_ok_bull = ((close > ema200) & (close > ema50)).fillna(False)
                    trend_ok_bear = ((close < ema200) & (close < ema50)).fillna(False)
                else:
                    trend_ok_bull = pd.Series(False, index=df.index)
                    trend_ok_bear = pd.Series(False, index=df.index)
                bull_raw = (bull_raw & trend_ok_bull).fillna(False)
                bear_raw = (bear_raw & trend_ok_bear).fillna(False)

            df["obtrade_long_confirm"] = concepts.first_signal_per_level(bull_raw, bull_ob_low)
            df["obtrade_short_confirm"] = concepts.first_signal_per_level(bear_raw, bear_ob_high)
            # SL: "a little below/above the Order Block zone" -- the zone's
            # own outer edge.
            df["obtrade_sl_bull"] = bull_ob_low
            df["obtrade_sl_bear"] = bear_ob_high
            # TP (not specified in source -- structure-based default,
            # "next significant opposite swing point"): the generic
            # entry_resistance/entry_support fallback turns out to be
            # structurally USELESS for an Order Block continuation trade
            # (confirmed directly against real trade data: 0/35 BTCUSDT
            # trades got a take-profit before this fix, a guaranteed-
            # loss-by-construction bug matching the exact failure mode
            # already documented elsewhere in this file) -- a bullish OB's
            # own swing "resistance" is, by definition, the OLD level price
            # already broke ABOVE to create this uptrend, so it sits BELOW
            # the current entry price and fails the generic branch's own
            # "zone > price" requirement on every single trade. A genuinely
            # forward reference is needed instead: the highest high (long)
            # / lowest low (short) of a wide rolling window, own default
            # 100 bars, standing in for "the next level price would need
            # to clear to keep going."
            df["obtrade_tp_bull"] = concepts.rolling_high(df["high"], 100)
            df["obtrade_tp_bear"] = concepts.rolling_low(df["low"], 100)

        _crt_used = {"crt_loose", "crt_strict"} & used
        if _crt_used:
            # New Batch 5, Strategy 7 (Candle Range Theory / CRT): single
            # timeframe (1H, source's own stated minimum). "Large red/green
            # candle" -- same body_pct>=50% momentum-candle convention as
            # Strategies 4/5/6, for consistency. CRH/CRL = that candle's
            # own high/low, held (ffilled) until the next qualifying
            # momentum candle redraws it -- own simplification of the
            # source's own "if the sweep fails, redraw the range on the
            # current candle" refinement (not built as a separate stateful
            # rule; a failed sweep simply leaves the existing range active
            # until the next genuine momentum candle appears, the same
            # "active zone" convention every other composite in this file
            # already uses).
            open_, close, high, low = df["open"], df["close"], df["high"], df["low"]
            body = (open_ - close).abs()
            rng = (high - low).replace(0, np.nan)
            body_pct = (body / rng).fillna(0.0) * 100.0
            large_red = ((close < open_) & (body_pct >= 50.0)).fillna(False)
            large_green = ((close > open_) & (body_pct >= 50.0)).fillna(False)
            crl = low.where(large_red).ffill()
            crh = high.where(large_green).ffill()

            # "Wait for the NEXT candle to move below CRL then close back
            # ABOVE CRL" -- concepts.liquidity_sweep()'s exact same-bar
            # wick-beyond-then-close-back-inside formula, copied against
            # this strategy's own CRL/CRH anchor instead of a same-frame
            # swing level (same technique as fractal_sweep_reversal's own
            # h4_support/h4_resistance copy).
            bull_sweep_reclaim = ((low < crl) & (close > crl)).fillna(False)
            bear_sweep_reclaim = ((high > crh) & (close < crh)).fillna(False)
            # "If the sweep candle is not a genuine long-wick candle,
            # discard the range" -- reuses Strategy 3's long_wick_candle()
            # unmodified, at the same 50% wick-fraction default.
            bull_wick, bear_wick = concepts.long_wick_candle(df)
            bull_ok = (bull_sweep_reclaim & bull_wick).fillna(False)
            bear_ok = (bear_sweep_reclaim & bear_wick).fillna(False)

            # Filter (source): "do NOT trade if the market is in a sideways
            # trend" -- same trend_regime() default as Strategies 3/4/9.
            trend = concepts.trend_regime(df)
            bull_ok = (bull_ok & (trend != "sideways")).fillna(False)
            bear_ok = (bear_ok & (trend != "sideways")).fillna(False)

            if "crt_strict" in used:
                # STRICT (shared checklist source with Strategy 6): EMA200
                # + EMA50 trend alignment, same convention as Strategy 6's
                # own strict gate, PLUS Fibonacci confirmation -- price
                # (at the CRT signal bar) sitting within a small ATR-scaled
                # band of the most recent swing's 50% or 61.8% retracement
                # level (concepts.fibonacci_retracement_zone() already only
                # computes 38.2/50/61.8 -- the 78%/23% levels the source
                # explicitly excludes were never options here at all, so
                # nothing extra needs disabling; 0%/100% are support/
                # resistance themselves, per that function's own docstring,
                # not separately checked here since the sweep-reclaim logic
                # already anchors directly to CRL/CRH).
                ema200 = df.get("ema_200")
                ema50 = df.get("ema_50")
                if ema200 is not None and ema50 is not None:
                    trend_ok_bull = ((close > ema200) & (close > ema50)).fillna(False)
                    trend_ok_bear = ((close < ema200) & (close < ema50)).fillna(False)
                else:
                    trend_ok_bull = pd.Series(False, index=df.index)
                    trend_ok_bear = pd.Series(False, index=df.index)
                if "atr_14" not in df.columns:
                    df["atr_14"] = concepts.atr(df, 14)
                fib_618, fib_50, _fib_382, _fib_dir = concepts.fibonacci_retracement_zone(df)
                near_fib = (
                    concepts.within_level_zone(df, fib_50, df["atr_14"], frac=0.25) |
                    concepts.within_level_zone(df, fib_618, df["atr_14"], frac=0.25)
                ).fillna(False)
                bull_ok = (bull_ok & trend_ok_bull & near_fib).fillna(False)
                bear_ok = (bear_ok & trend_ok_bear & near_fib).fillna(False)

            df["crt_long_confirm"] = bull_ok
            df["crt_short_confirm"] = bear_ok
            # SL: "below CRL" (long, explicit) / "a little above CRH"
            # (short, explicit "a little" -- standard buffer).
            df["crt_sl_bull"] = crl
            df["crt_sl_bear"] = crh

        if "bos_choch_retest" in used:
            # New Batch 5, Strategy 8 (BOS/CHoCH Structure Break + Strong
            # Level Retest -- narrowed, mechanical extraction). "HH/HL vs
            # LH/LL trend, BOS = continuation break, CHoCH = reversal
            # break" are exactly concepts.break_of_structure()/change_of_
            # character(), reused unmodified. "Strong Level" = the swing
            # level that got broken (support_resistance()'s own resistance/
            # support at the break bar), held until the break is retested
            # -- same "broken level -> retest via reaction_at_level() ->
            # sequential_event() ordering" composition the existing
            # mss_reversal strategy already uses for its own CHoCH-only
            # case, generalized here to (BOS | CHoCH) since the source
            # treats both as "a break that creates a Strong Level to
            # retest," not just reversals. "Do not assume a CHoCH is valid
            # until the confirming candle is fully closed" is already
            # guaranteed by construction -- every concept here only ever
            # reads fully-closed bars, no intra-bar state exists to jump
            # the gun on.
            if "support" not in df.columns:
                df["support"], df["resistance"] = concepts.support_resistance(df)
            support, resistance = df["support"], df["resistance"]
            bullish_bos, bearish_bos = concepts.break_of_structure(df)
            bullish_choch, bearish_choch = concepts.change_of_character(df)
            bull_break_event = (bullish_bos | bullish_choch).fillna(False)
            bear_break_event = (bearish_bos | bearish_choch).fillna(False)

            strong_level_bull = resistance.where(bull_break_event).ffill()
            strong_level_bear = support.where(bear_break_event).ffill()
            bull_retest, bear_retest = concepts.reaction_at_level(df, strong_level_bull, strong_level_bear)
            # max_gap=30 1h bars (~5 trading days): own default -- the
            # source requires a retest but gives no exact reaction window.
            df["bosc_long_confirm"] = concepts.sequential_event(bull_break_event, bull_retest, max_gap=30)
            df["bosc_short_confirm"] = concepts.sequential_event(bear_break_event, bear_retest, max_gap=30)
            # SL: "slightly below/above the Strong Level" -- the broken
            # level itself.
            df["bosc_sl_bull"] = strong_level_bull
            df["bosc_sl_bear"] = strong_level_bear
            # TP (not specified in source -- structure-based default,
            # "next opposite significant swing point"): reuses Strategy 6's
            # own fix directly -- the generic entry_resistance/entry_
            # support fallback is the SAME kind of already-broken,
            # behind-price level a continuation retest would hit (confirmed
            # bug pattern, not re-derived here), so a genuinely forward
            # 100-bar rolling high/low is used instead, same as Strategy 6.
            df["bosc_tp_bull"] = concepts.rolling_high(df["high"], 100)
            df["bosc_tp_bear"] = concepts.rolling_low(df["low"], 100)

        if "ichimoku_system" in used:
            # New Batch 5, Strategy 9 (Ichimoku Cloud System). Shared by
            # all 4 timeframe variants and both exit-mode variants (8
            # combinations) -- only the StrategyConfig's own timeframes/
            # exit_conditions/trailing_stop differ, not this block.
            conversion, base, span_a, span_b, lag_above, lag_below = concepts.ichimoku_cloud(df)
            cross_above_event = ((conversion > base) & ~(conversion.shift(1) > base.shift(1))).fillna(False)
            cross_below_event = ((conversion < base) & ~(conversion.shift(1) < base.shift(1))).fillna(False)
            df["ichimoku_cross_above"] = cross_above_event
            df["ichimoku_cross_below"] = cross_below_event

            conversion_above_state = (conversion > base)
            cloud_green = (span_a > span_b)
            cloud_red = (span_a < span_b)
            # "Ordering rule (STRICT): all three confirmations must align
            # together -- do not enter on the crossover alone." Edge-
            # triggered on the combined AND of all three STATES (not a
            # sequential_event() ordering of two distinct events): fires
            # exactly once, on whichever bar all three first become
            # simultaneously true -- "may be the crossover candle itself
            # or a subsequent one" (source's own exact wording for the
            # short case, applied symmetrically to longs too since the
            # underlying logic doesn't differ).
            bull_aligned = (conversion_above_state & lag_above & cloud_green).fillna(False)
            bear_aligned = (~conversion_above_state & lag_below & cloud_red).fillna(False)
            bull_raw = (bull_aligned & ~bull_aligned.shift(1).fillna(False)).fillna(False)
            bear_raw = (bear_aligned & ~bear_aligned.shift(1).fillna(False)).fillna(False)

            # Filter: "do NOT use in a sideways market" -- same
            # trend_regime() default as Strategies 3/4/7.
            trend = concepts.trend_regime(df)
            df["ichimoku_long_confirm"] = (bull_raw & (trend != "sideways")).fillna(False)
            df["ichimoku_short_confirm"] = (bear_raw & (trend != "sideways")).fillna(False)
            # SL: "below/above the candle in which the crossover occurred"
            # -- held from the crossover event until the (possibly later)
            # aligned entry consumes it.
            df["ichimoku_sl_bull"] = df["low"].where(cross_above_event).ffill()
            df["ichimoku_sl_bear"] = df["high"].where(cross_below_event).ffill()

        if "fvg_equilibrium_entry" in used:
            # New Batch 4, Strategy 4 (FVG 50% Equilibrium Entry): reuses
            # fair_value_gap()/fvg_zone() entirely, no new detection logic.
            # Single-timeframe (1H, per the source).
            if "fvg_bull_low" not in df.columns:
                (df["fvg_bull_low"], df["fvg_bull_high"],
                 df["fvg_bear_low"], df["fvg_bear_high"]) = concepts.fvg_zone(df)
            if "bull_fvg" not in df.columns:
                df["bull_fvg"], df["bear_fvg"] = concepts.fair_value_gap(df)
            if "atr_14" not in df.columns:
                df["atr_14"] = concepts.atr(df, 14)
            atr14 = df["atr_14"]
            fvg_bull_low, fvg_bull_high = df["fvg_bull_low"], df["fvg_bull_high"]
            fvg_bear_low, fvg_bear_high = df["fvg_bear_low"], df["fvg_bear_high"]
            # Skip small/low-quality gaps -- own default minimum gap size,
            # 0.1x ATR(14), the same style of ATR-scaled quality floor this
            # codebase already uses elsewhere (e.g. imbalance()'s body
            # threshold).
            min_gap = 0.1 * atr14
            bull_gap_ok = ((fvg_bull_high - fvg_bull_low) >= min_gap).fillna(False)
            bear_gap_ok = ((fvg_bear_high - fvg_bear_low) >= min_gap).fillna(False)
            fvg_bull_mid = (fvg_bull_low + fvg_bull_high) / 2.0
            fvg_bear_mid = (fvg_bear_low + fvg_bear_high) / 2.0
            close = df["close"]
            touch_mid_bull = ((close <= fvg_bull_mid) & (close.shift(1) > fvg_bull_mid.shift(1))).fillna(False)
            touch_mid_bear = ((close >= fvg_bear_mid) & (close.shift(1) < fvg_bear_mid.shift(1))).fillna(False)
            df["fvg_eq_long_confirm"] = concepts.first_signal_per_level(
                (touch_mid_bull & bull_gap_ok).fillna(False), fvg_bull_low)
            df["fvg_eq_short_confirm"] = concepts.first_signal_per_level(
                (touch_mid_bear & bear_gap_ok).fillna(False), fvg_bear_high)
            # SL: "slightly beyond the FVG zone; if the FVG-producing candle
            # is small, use that candle's high/low instead" -- the
            # FVG-producing/impulse candle is bar i-1 relative to the gap's
            # own confirmation bar i (classic 3-candle FVG shape, same
            # reasoning as htf_ltf_fvg_ob_confluence's SL refinement in
            # prepare() below, just the OPPOSITE size condition: small
            # instead of large). "Small" -- own default, the same 1.5x
            # ATR(14) threshold used there, just inverted.
            origin_range = (df["high"].shift(1) - df["low"].shift(1))
            gap_formed_bull = (fvg_bull_low != fvg_bull_low.shift(1)) & fvg_bull_low.notna()
            gap_formed_bear = (fvg_bear_high != fvg_bear_high.shift(1)) & fvg_bear_high.notna()
            origin_at_formation_bull = origin_range.where(gap_formed_bull).ffill()
            origin_at_formation_bear = origin_range.where(gap_formed_bear).ffill()
            is_small_bull = (origin_at_formation_bull < 1.5 * atr14).fillna(False)
            is_small_bear = (origin_at_formation_bear < 1.5 * atr14).fillna(False)
            candle_low_at_formation = df["low"].shift(1).where(gap_formed_bull).ffill()
            candle_high_at_formation = df["high"].shift(1).where(gap_formed_bear).ffill()
            df["fvg_eq_sl_bull"] = candle_low_at_formation.where(is_small_bull, fvg_bull_low)
            df["fvg_eq_sl_bear"] = candle_high_at_formation.where(is_small_bear, fvg_bear_high)
        if "donchian_lwti_volume_confluence" in used:
            # New Batch 4, Strategy 5: the LWTI + Volume confirmation legs
            # of the 3-part sequence run on WHATEVER frame this runs on --
            # for this strategy that's always the entry (15m) role (the
            # Donchian breakout itself is a separate bias(1H)-role gate,
            # computed in prepare_context, combined with these two here in
            # prepare() post-merge).
            df["lwti"] = concepts.lwti(df, period=25, smoothing=20)
            df["volume_ma_30"] = concepts.sma(df["volume"], 30)
        if {"demand_zone", "supply_zone"} & used:
            (df["demand_low"], df["demand_high"],
             df["supply_low"], df["supply_high"]) = concepts.consolidation_impulse_zones(df, **zone_params)
        if "valid_structure_trend" in used:
            df["structure_trend"] = concepts.valid_structure_trend(df)
            # Liquidity Sweep Reversal's SOFT bias filter: "the reclaim
            # should align with the broader bias not being STRONGLY
            # bearish" -- explicitly NOT "must be strongly bullish" (this
            # is a reversal setup that can occur against short-term
            # bearish pressure). No existing concept expresses a negation
            # ("trend != down") -- valid_structure_trend's own eval only
            # ever checks equality to "up"/"down". These two columns (used
            # via the new "valid_structure_trend_soft" concept name below)
            # are the minimal addition for that -- harmless for every
            # other strategy since nothing else references them.
            df["trend_not_down"] = (df["structure_trend"] != "down")
            df["trend_not_up"] = (df["structure_trend"] != "up")
        if "mss_reversal" in used:
            # Market Structure Shift Reversal strategy: uses the MORE
            # RIGOROUS of the two existing CHoCH implementations the
            # Concepts Library entry itself names -- valid_structure_trend()
            # (a genuinely stateful "a low only counts once the prior high
            # is broken" machine) instead of the simpler change_of_character
            # (a same-window BOS-direction-flip check) -- per the task's own
            # explicit instruction to prefer the stricter one, flagged here.
            # The break event is the bar structure_trend actually FLIPS to
            # "up"/"down" (edge-triggered on the state machine's own output,
            # not re-derived). Entry uses the RETEST version (this library's
            # documented default): the broken level is captured at the
            # break bar as the swing high/low support_resistance() already
            # tracks (a bullish break's broken level IS df["resistance"] at
            # that bar, since valid_structure_trend's own break condition is
            # "close > the swing high level", the same swing high
            # support_resistance() forward-fills), held constant via ffill
            # until the next break, then reaction_at_level() -- already
            # built for Dumb Money Concepts' identical "wick beyond a level,
            # close back inside" reaction shape -- reused directly for the
            # retest reaction itself. sequential_event() enforces the retest
            # strictly AFTER the break, using the real per-bar ordering
            # primitive (not a same-window approximation) -- exactly the
            # class of bug this session's sequential_event() same-bar-
            # overlap fix addressed.
            if "support" not in df.columns:
                df["support"], df["resistance"] = concepts.support_resistance(df)
            trend_s = df["structure_trend"]
            bull_break_event = ((trend_s == "up") & (trend_s.shift(1) != "up")).fillna(False)
            bear_break_event = ((trend_s == "down") & (trend_s.shift(1) != "down")).fillna(False)
            broken_res_level = df["resistance"].where(bull_break_event).ffill()
            broken_sup_level = df["support"].where(bear_break_event).ffill()
            bull_retest, bear_retest = concepts.reaction_at_level(df, broken_res_level, broken_sup_level)
            df["mss_long_confirm"] = concepts.sequential_event(bull_break_event, bull_retest)
            df["mss_short_confirm"] = concepts.sequential_event(bear_break_event, bear_retest)
        if "liquidity_sweep_reclaim" in used:
            # Liquidity Sweep Reversal Strategy: sweep-then-reclaim of the
            # nearest swing S/R level, sequence-ordered. Computed on
            # WHICHEVER role's frame this runs on (same as every other
            # concept here) -- for this strategy that's the entry (15m)
            # frame directly, an approximation flagged in the report: the
            # source separately wants "1H for identifying MAJOR highs/
            # lows," but concept columns are computed per-role BEFORE the
            # cross-timeframe merge, so a 15m concept can't reference an
            # already-merged 1H level at this stage -- doing so would need
            # a new architecture capability, out of scope here.
            bull_sweep, bear_sweep, bull_reclaim, bear_reclaim = concepts.level_sweep_reclaim(df)
            df["level_long_confirm"] = concepts.sequential_event(bull_sweep, bull_reclaim)
            df["level_short_confirm"] = concepts.sequential_event(bear_sweep, bear_reclaim)
        if "volume" in used and "volume_spike" not in df.columns:
            df["volume_spike"] = concepts.volume_filter(df)
        if {"pdh", "pdl", "pdh_sweep", "pdl_sweep"} & used:
            df["pdh"], df["pdl"] = concepts.previous_day_high_low(df)
        if {"pdh_sweep", "pdl_sweep"} & used:
            df["pdl_sweep"], df["pdh_sweep"] = concepts.pdh_pdl_sweep(df)
        if "pdhl_reversal" in used:
            # Previous High/Low Reversal strategy: the Concepts Library's
            # own entry flags that no existing function combines the
            # day-boundary level (previous_day_high_low()) with a SEQUENCE-
            # ORDERED reclaim (pdh_pdl_sweep() is same-bar wick-and-close-
            # back only) -- this is exactly that small composition, built
            # following the identical pattern already established for
            # session_sweep_reclaim()/level_sweep_reclaim() (sweep and
            # reclaim as separate boolean series, edge-triggered on the
            # reclaim's own close-transition, combined via
            # sequential_event() for genuine strict ordering).
            if "pdh" not in df.columns:
                df["pdh"], df["pdl"] = concepts.previous_day_high_low(df)
            low, high, close = df["low"], df["high"], df["close"]
            bull_sweep = (low < df["pdl"]).fillna(False)
            bear_sweep = (high > df["pdh"]).fillna(False)
            was_below = (close.shift(1) <= df["pdl"].shift(1)).fillna(False)
            was_above = (close.shift(1) >= df["pdh"].shift(1)).fillna(False)
            bull_reclaim = ((close > df["pdl"]) & was_below).fillna(False)
            bear_reclaim = ((close < df["pdh"]) & was_above).fillna(False)
            df["pdhl_long_confirm"] = concepts.sequential_event(bull_sweep, bull_reclaim)
            df["pdhl_short_confirm"] = concepts.sequential_event(bear_sweep, bear_reclaim)
        if "fvg" in used:
            (df["fvg_bull_low"], df["fvg_bull_high"],
             df["fvg_bear_low"], df["fvg_bear_high"]) = concepts.fvg_zone(df)
        if "fvg_reversal" in used:
            # Fair Value Gap Reversal strategy: the Concepts Library's FVG
            # entry describes a TWO-step entry ("price returns into the gap,
            # THEN a later candle closes back in the original move's
            # direction") plus a freshness requirement ("a fresh/unfilled
            # gap is stronger than a partially-filled one") -- neither is
            # what the existing "fvg_zone" concept (used by CRT 2.0) checks,
            # which only fires on the FIRST step (an edge-triggered arrival
            # into the zone, containment only, no reaction/no freshness-
            # across-visits tracking). Both missing pieces are built here
            # from 100% existing primitives, no new capability:
            #   - "tag" (arrival into the zone): the same outside->inside
            #     edge-trigger fvg_zone's own _eval dispatch already uses,
            #     just as a real column instead of an inline per-bar check.
            #   - "reaction" (closes back toward the original direction):
            #     candle_pattern_confirmation() reused directly -- it is
            #     EXACTLY "pattern fires, then a later candle closes beyond
            #     the pattern candle's own high/low," which is precisely
            #     what "closes back in the direction of the move" means
            #     here (also naturally guarantees the sequence-ordering the
            #     spec asks for, via ffill causality -- a tag can only ever
            #     fire once fvg_bull_low/high exist, i.e. strictly after the
            #     gap has formed, same reasoning as Laxman Rekha's trigger).
            #   - freshness ("fresh gap preferred over already-tagged one"):
            #     represented as a hard once-per-gap filter via
            #     first_signal_per_level(), the exact same "once-tested"
            #     pattern already used for DMC's levels and Order Block's
            #     retest -- the gap's own low/high value (constant for that
            #     gap's whole lifetime via ffill) is a stable identity key.
            if "bull_fvg" not in df.columns:
                df["bull_fvg"], df["bear_fvg"] = concepts.fair_value_gap(df)
            if "fvg_bull_low" not in df.columns:
                (df["fvg_bull_low"], df["fvg_bull_high"],
                 df["fvg_bear_low"], df["fvg_bear_high"]) = concepts.fvg_zone(df)
            close = df["close"]
            bull_inside = ((close >= df["fvg_bull_low"]) & (close <= df["fvg_bull_high"])).fillna(False)
            bull_tag = bull_inside & ~bull_inside.shift(1).fillna(False)
            bear_inside = ((close >= df["fvg_bear_low"]) & (close <= df["fvg_bear_high"])).fillna(False)
            bear_tag = bear_inside & ~bear_inside.shift(1).fillna(False)
            raw_long = concepts.candle_pattern_confirmation(bull_tag, df, "bullish")
            raw_short = concepts.candle_pattern_confirmation(bear_tag, df, "bearish")
            df["fvg_reversal_long_confirm"] = concepts.first_signal_per_level(raw_long, df["fvg_bull_low"])
            df["fvg_reversal_short_confirm"] = concepts.first_signal_per_level(raw_short, df["fvg_bear_low"])
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
        if "premium_discount_zone" in used:
            df["in_discount"], df["in_premium"] = concepts.premium_discount_zone(df)
        if "rejection_block" in used:
            rbl, rbh, rrbl, rrbh = concepts.rejection_blocks(df)
            df["bull_rejection_low"], df["bull_rejection_high"] = rbl, rbh
            df["bear_rejection_low"], df["bear_rejection_high"] = rrbl, rrbh
        if "orb" in used:
            df["bull_orb"], df["bear_orb"] = concepts.opening_range_breakout(df)
        if "initial_balance" in used:
            df["ib_above"], df["ib_below"] = concepts.initial_balance_extension(df)
        if "kill_zone" in used:
            df["in_kill_zone"] = concepts.in_kill_zone(df)
        if "sniper_headshot_entry" in used:
            # Sniper Headshot Entry: obvious-level sweep (liquidity_sweep,
            # already anchored to confirmed swing S/R -- the mechanical
            # proxy for "an obvious retail level"), THEN price taps into a
            # Demand/Supply zone, THEN a Hammer OR strong same-direction
            # candle confirms -- three genuinely sequence-ordered stages,
            # chained via two sequential_event() calls (same composition
            # pattern as mss_reversal's break-then-retest above). Primary
            # entry only, per the task's own explicit exclusion of the
            # pyramiding second entry (single-entry/single-exit model).
            if "bull_liquidity_sweep" not in df.columns:
                df["bull_liquidity_sweep"], df["bear_liquidity_sweep"] = concepts.liquidity_sweep(df)
            if "demand_low" not in df.columns:
                (df["demand_low"], df["demand_high"],
                 df["supply_low"], df["supply_high"]) = concepts.consolidation_impulse_zones(df, **zone_params)
            if "bull_pin_bar" not in df.columns:
                df["bull_pin_bar"], df["bear_pin_bar"] = concepts.pin_bar(df)
            close = df["close"]
            bull_in_zone = ((close >= df["demand_low"]) & (close <= df["demand_high"])).fillna(False)
            bear_in_zone = ((close >= df["supply_low"]) & (close <= df["supply_high"])).fillna(False)
            # Edge-triggered arrival into the zone (outside->inside), same
            # fix as fvg_zone's own dispatch and Strategy 1's htf_key_level_
            # engulfing above -- plain containment would satisfy the "tap"
            # requirement for every bar price merely sits inside the zone.
            bull_zone_tap = (bull_in_zone & ~bull_in_zone.shift(1).fillna(False)).fillna(False)
            bear_zone_tap = (bear_in_zone & ~bear_in_zone.shift(1).fillna(False)).fillna(False)
            # "Hammer OR strong bullish/bearish candle" confirmation, per
            # the strategy's own wording -- pin_bar() already IS Hammer/
            # Shooting Star; "strong candle" (own default: body >= 60% of
            # its own range, since the source gives no exact number, same
            # own-default style as candle_body_pct's other callers) is the
            # plain-candle alternative when no proper Hammer forms.
            body = (df["close"] - df["open"]).abs()
            rng = (df["high"] - df["low"]).replace(0, float("nan"))
            body_pct = (body / rng).fillna(0.0) * 100.0
            strong_bull = ((df["close"] > df["open"]) & (body_pct >= 60.0)).fillna(False)
            strong_bear = ((df["close"] < df["open"]) & (body_pct >= 60.0)).fillna(False)
            confirm_bull = (df["bull_pin_bar"] | strong_bull).fillna(False)
            confirm_bear = (df["bear_pin_bar"] | strong_bear).fillna(False)
            # max_gap own defaults (20 bars ~= 100 min for sweep->zone-tap,
            # 10 bars ~= 50 min for zone-tap->confirmation candle): the
            # source gives no exact number for either reaction window, same
            # reasoning as Strategy 1's own max_gap choice.
            sweep_then_zone_bull = concepts.sequential_event(df["bull_liquidity_sweep"], bull_zone_tap, max_gap=20)
            sweep_then_zone_bear = concepts.sequential_event(df["bear_liquidity_sweep"], bear_zone_tap, max_gap=20)
            df["sniper_long_confirm"] = concepts.sequential_event(sweep_then_zone_bull, confirm_bull, max_gap=10)
            df["sniper_short_confirm"] = concepts.sequential_event(sweep_then_zone_bear, confirm_bear, max_gap=10)
        if used & _CANDLESTICK_PATTERN_CONCEPTS:
            # Gate was `if "candlestick_patterns" in used:` -- the umbrella
            # name ONLY. But validator.known_indicator_names() advertises
            # each individual pattern too (doji_confirm, hammer_confirm,
            # shooting_star_confirm, morning_star, evening_star), so the
            # Strategy Wizard offers them and the AI importer can emit
            # them. A strategy declaring only its own pattern name got
            # these columns never computed, and the matching event_colmap
            # entries below then read a column that did not exist --
            # silently False on every bar, forever. Same declared-but-dead
            # bug class as the VWAP and MACD gaps (tracker #1/#4).
            # Measured on 17,181 real BTCUSDT 5m bars, own-name-only vs
            # with the umbrella also declared: doji_confirm 0 -> 9528,
            # hammer_confirm 0 -> 11152, shooting_star_confirm 0 -> 11289,
            # morning_star 0 -> 5643, evening_star 0 -> 5563.
            # Purely widening: every strategy that already declares
            # "candlestick_patterns" still matches and is unaffected.
            # Candlestick Pattern Reversal Strategy: single-candle patterns
            # (Doji/Hammer/Shooting Star) need a later confirmation candle,
            # sequence-ordered; Engulfing (already wired below via
            # "engulfing") and the new 3-candle Star patterns are
            # self-confirming. pin_bar() with the strategy's own defaults
            # (wick_ratio=2.0, body_ratio=0.3) IS Hammer (bull_pin) /
            # Shooting Star (bear_pin) -- reused directly rather than
            # duplicating the same geometry under a new name.
            doji = concepts.doji_pattern(df, max_body_pct=10.0)
            bull_pin, bear_pin = concepts.pin_bar(df, wick_ratio=2.0, body_ratio=0.3)
            morning_star, evening_star = concepts.morning_evening_star(df, small_body_max_pct=30.0)
            df["doji_event"] = doji
            df["hammer_event"] = bull_pin
            df["shooting_star_event"] = bear_pin
            df["morning_star_event"] = morning_star
            df["evening_star_event"] = evening_star
            df["doji_confirm_bull"] = concepts.candle_pattern_confirmation(doji, df, "bullish")
            df["doji_confirm_bear"] = concepts.candle_pattern_confirmation(doji, df, "bearish")
            df["hammer_confirm"] = concepts.candle_pattern_confirmation(bull_pin, df, "bullish")
            df["shooting_star_confirm"] = concepts.candle_pattern_confirmation(bear_pin, df, "bearish")
            # Pattern-candle's own extreme, carried forward for the stop-
            # loss to read at the LATER confirmation bar (Doji/Hammer/
            # Shooting Star) -- prepended to _compute_stop_loss()'s
            # "structure" candidate chain below. Morning/Evening Star's own
            # extreme is read directly at the pattern's own (= entry) bar,
            # no forward-fill needed.
            df["doji_pending_low"] = df["low"].where(doji).ffill()
            df["doji_pending_high"] = df["high"].where(doji).ffill()
            df["hammer_pending_low"] = df["low"].where(bull_pin).ffill()
            df["shooting_star_pending_high"] = df["high"].where(bear_pin).ffill()
            df["morning_star_low"] = df["low"].rolling(3).min()
            df["evening_star_high"] = df["high"].rolling(3).max()
        if "four_hour_range_reentry" in used:
            # 4-Hour Range Breakout-Retest's sequence: a full-body close
            # beyond the day's first-4h range, THEN a later close back
            # inside it (edge-triggered, not "still inside"), strictly in
            # that order and constrained to the SAME New-York trading day
            # (concepts.sequential_event's reset_key -- an evening breakout
            # with no same-day re-entry must NOT pair with a coincidental
            # inside-range close on a LATER day).
            range_high, range_low = concepts.four_hour_range(df)
            bull_break, bear_break = concepts.four_hour_range_breakout(df)
            re_entry = concepts.range_reentry_event(df, range_high, range_low)
            day_key = pd.Series(df.index.tz_convert("America/New_York").date, index=df.index)
            df["range_long_confirm"] = concepts.sequential_event(bear_break, re_entry, reset_key=day_key)
            df["range_short_confirm"] = concepts.sequential_event(bull_break, re_entry, reset_key=day_key)
        if "asian_range_sweep_reclaim" in used:
            # Asian Range London Sweep: sweep of the closed Asian session's
            # range, THEN a later reclaim back inside, strictly in that
            # order (day-scoped, same reasoning as four_hour_range_reentry
            # above).
            bull_sweep, bear_sweep, bull_reclaim, bear_reclaim = concepts.session_sweep_reclaim(df, "asian")
            day_key2 = pd.Series(df.index.date, index=df.index)
            df["asian_long_confirm"] = concepts.sequential_event(bull_sweep, bull_reclaim, reset_key=day_key2)
            df["asian_short_confirm"] = concepts.sequential_event(bear_sweep, bear_reclaim, reset_key=day_key2)
        if "laxman_trigger" in used:
            # Laxman Rekha 5-EMA: a trigger candle entirely below/above the
            # 5 EMA (no touch), nullified/replaced by a NEWER qualifying
            # trigger candle if one forms before the current one breaks --
            # candle_pattern_confirmation()'s pending_level is a ffill of
            # the LATEST trigger event's own high/low, so a fresh trigger
            # candle automatically supersedes the pending one for free (the
            # same mechanism already used for Doji/Hammer/Shooting Star
            # confirmation), giving genuine nullification without a new
            # state machine. Runs on whichever role's own frame this is
            # called against (entry=5m for longs, short_tf=15m for shorts
            # -- two different entry timeframes per direction, see
            # StrategyConfig.timeframes_by_role for this strategy).
            ema5 = df.get("ema_5")
            if ema5 is not None:
                no_touch_below, no_touch_above = concepts.ema_no_touch_trigger(df, ema5)
                df["laxman_long_confirm"] = concepts.candle_pattern_confirmation(no_touch_below, df, "bullish")
                df["laxman_short_confirm"] = concepts.candle_pattern_confirmation(no_touch_above, df, "bearish")
                df["laxman_trigger_low"] = df["low"].where(no_touch_below).ffill()
                df["laxman_trigger_high"] = df["high"].where(no_touch_above).ffill()
        if (_DMC_VARIANTS & used) and ({"support", "resistance"} - set(df.columns)):
            # Dumb Money Concepts' level source (Monthly/Weekly/Daily
            # collapsed to Daily -- see prepare_context()'s comment on this
            # role) needs its own support/resistance computed here even
            # though nothing else in `used` already triggers it on this
            # specific frame.
            df["support"], df["resistance"] = concepts.support_resistance(df)
        if _DMC_VARIANTS & used:
            df["next_prior_swing_low"], df["next_prior_swing_high"] = concepts.next_prior_swing_level(df)
            (df["move_origin_for_support"],
             df["move_origin_for_resistance"]) = concepts.move_origin_target(df)

    @staticmethod
    def _compute_role_zone_columns(role_df):
        """HTF Key Level Engulfing Reversal: Order Block / FVG / Liquidity
        Sweep zones computed directly on a role's OWN raw frame (1H or 15M),
        the same primitives every other strategy already uses (order_blocks,
        fvg_zone, liquidity_sweep) -- just called here explicitly because
        this strategy needs them on TWO non-entry roles at once (h1 AND
        m15), which the normal `used`-driven per-role loop in
        prepare_context() only does for roles a plain Condition references
        (this strategy's "key level tap" isn't a plain Condition -- see the
        prepare() block below), not for a bespoke multi-role combination."""
        if "bull_ob_low" not in role_df.columns:
            bl, bh, brl, brh = concepts.order_blocks(role_df)
            role_df["bull_ob_low"], role_df["bull_ob_high"] = bl, bh
            role_df["bear_ob_low"], role_df["bear_ob_high"] = brl, brh
        if "fvg_bull_low" not in role_df.columns:
            (role_df["fvg_bull_low"], role_df["fvg_bull_high"],
             role_df["fvg_bear_low"], role_df["fvg_bear_high"]) = concepts.fvg_zone(role_df)
        if "bull_liquidity_sweep" not in role_df.columns:
            role_df["bull_liquidity_sweep"], role_df["bear_liquidity_sweep"] = concepts.liquidity_sweep(role_df)

    # -------------------------------------------------- Strategy interface
    def prepare(self, df):
        # engine.run_backtest expects plain open/high/low/close/volume
        # columns; alias them from the entry timeframe's prefixed columns
        # so the existing (unmodified) engine works unchanged.
        for col in ("open", "high", "low", "close", "volume"):
            entry_col = f"entry_{col}"
            if entry_col in df.columns and col not in df.columns:
                df[col] = df[entry_col]

        if "dmc_confirmation" in self.config.concepts_used:
            # Dumb Money Concepts' reaction-then-retest confirmation: the
            # entry (4H) timeframe's OWN candles checked against the
            # higher-timeframe (daily_tf) support/resistance level, which
            # only exist together on the SAME frame here, after ctx.build()
            # has already merge_asof'd daily_tf_* onto the entry index --
            # this is genuinely not computable inside _compute_concept_
            # columns() (that runs per-role BEFORE the merge). Reaction and
            # retest are the identical pattern reused twice via
            # sequential_event(reaction, reaction): fires only if that same
            # pattern also fired at some strictly earlier bar -- the second,
            # later occurrence IS the retest. first_signal_per_level() then
            # enforces "each specific level can only trigger one trade."
            support_lvl = df.get("daily_tf_support")
            resistance_lvl = df.get("daily_tf_resistance")
            if support_lvl is not None and resistance_lvl is not None:
                bull_reaction, bear_reaction = concepts.reaction_at_level(df, support_lvl, resistance_lvl)
                raw_long_confirm = concepts.sequential_event(bull_reaction, bull_reaction)
                raw_short_confirm = concepts.sequential_event(bear_reaction, bear_reaction)
                df["entry_dmc_long_confirm"] = concepts.first_signal_per_level(raw_long_confirm, support_lvl)
                df["entry_dmc_short_confirm"] = concepts.first_signal_per_level(raw_short_confirm, resistance_lvl)

        if "dmc_blind_entry" in self.config.concepts_used:
            # Dumb Money Concepts -- Blind Entry: same untested-level
            # detection as Confirmation, but no reaction/retest gate at
            # all -- enter the instant price first reaches the level.
            support_lvl = df.get("daily_tf_support")
            resistance_lvl = df.get("daily_tf_resistance")
            if support_lvl is not None and resistance_lvl is not None:
                bull_touch, bear_touch = concepts.level_touch(df, support_lvl, resistance_lvl)
                df["entry_dmc_long_confirm"] = concepts.first_signal_per_level(bull_touch, support_lvl)
                df["entry_dmc_short_confirm"] = concepts.first_signal_per_level(bear_touch, resistance_lvl)

        if "dmc_combined" in self.config.concepts_used:
            # Dumb Money Concepts -- Combined Confirmation: reaction, THEN
            # a sequence-ordered retest (identical to Confirmation), PLUS
            # the retest bar's close must also fall within a small ATR-
            # scaled zone-buffer band around the level -- a single-entry
            # approximation of the source's DCA-zone concept (see
            # concepts.within_level_zone's own docstring; real multi-entry
            # DCA remains excluded, gap #14).
            support_lvl = df.get("daily_tf_support")
            resistance_lvl = df.get("daily_tf_resistance")
            if support_lvl is not None and resistance_lvl is not None:
                bull_reaction, bear_reaction = concepts.reaction_at_level(df, support_lvl, resistance_lvl)
                raw_long_confirm = concepts.sequential_event(bull_reaction, bull_reaction)
                raw_short_confirm = concepts.sequential_event(bear_reaction, bear_reaction)
                atr14 = concepts.atr(df, 14)
                long_in_zone = concepts.within_level_zone(df, support_lvl, atr14)
                short_in_zone = concepts.within_level_zone(df, resistance_lvl, atr14)
                raw_long_confirm = raw_long_confirm & long_in_zone
                raw_short_confirm = raw_short_confirm & short_in_zone
                df["entry_dmc_long_confirm"] = concepts.first_signal_per_level(raw_long_confirm, support_lvl)
                df["entry_dmc_short_confirm"] = concepts.first_signal_per_level(raw_short_confirm, resistance_lvl)

        if "htf_key_level_engulfing" in self.config.concepts_used:
            # HTF Key Level Engulfing Reversal: bias (Daily/4H/1H EMA50
            # trend, own default -- source gives no exact bias mechanism) +
            # "key level tap" (price back inside an OB/FVG zone marked on
            # 1H or 15M, or a recent 1H/15M liquidity sweep) can only be
            # computed HERE, post-merge (same reasoning as the DMC blocks
            # above): it reads several different roles' columns together on
            # the SAME (entry) frame, which only exist together after
            # ctx.build()'s merge_asof.
            daily_close, daily_ema = df.get("daily_close"), df.get("daily_ema_50")
            h4_close, h4_ema = df.get("h4_close"), df.get("h4_ema_50")
            h1_close, h1_ema = df.get("h1_close"), df.get("h1_ema_50")
            if all(x is not None for x in (daily_close, daily_ema, h4_close, h4_ema, h1_close, h1_ema)):
                daily_up = daily_close > daily_ema
                h4_up = h4_close > h4_ema
                h1_up = h1_close > h1_ema
                # Conflict filter: skip the setup entirely if 4H and 1H bias
                # directly oppose each other. EMA-slope trend has no
                # "neutral" state (always up or down), so the source's "if
                # one is neutral, 4H takes priority" branch never actually
                # triggers with this bias mechanism -- flagged in the
                # report rather than silently assumed. Daily is read for
                # context/description only; only 4H vs 1H is a hard gate,
                # per the strategy's own explicit wording.
                conflict_ok = (h4_up == h1_up).fillna(False)
                bias_bull = (conflict_ok & h4_up).fillna(False)
                bias_bear = (conflict_ok & ~h4_up).fillna(False)
            else:
                bias_bull = pd.Series(False, index=df.index)
                bias_bear = pd.Series(False, index=df.index)

            def _zone_tap(prefix):
                lo, hi = df.get(f"{prefix}_low"), df.get(f"{prefix}_high")
                if lo is None or hi is None:
                    return pd.Series(False, index=df.index)
                close = df["close"]
                return ((close >= lo) & (close <= hi)).fillna(False)

            def _sweep_recent(col, window=3):
                # "Any True in the last `window` bars including this one" --
                # a plain backward-looking rolling max, causal by
                # construction (rolling() never sees future bars).
                s = df.get(col)
                if s is None:
                    return pd.Series(False, index=df.index)
                return s.fillna(False).astype(float).rolling(window, min_periods=1).max().astype(bool)

            bull_in_zone = (_zone_tap("h1_bull_ob") | _zone_tap("h1_fvg_bull")
                            | _zone_tap("m15_bull_ob") | _zone_tap("m15_fvg_bull"))
            bear_in_zone = (_zone_tap("h1_bear_ob") | _zone_tap("h1_fvg_bear")
                            | _zone_tap("m15_bear_ob") | _zone_tap("m15_fvg_bear"))
            # Edge-triggered arrival into the zone (outside->inside), not
            # plain containment -- same fix already applied to fvg_zone's
            # own dispatch (see the fvg_zone comment above): plain
            # containment fires on EVERY bar price sits inside a zone,
            # which combined with sequential_event's "most recent earlier
            # occurrence carries forward" semantics would make the tap
            # requirement satisfied by almost any zone visit in the whole
            # backtest history, not a genuine "price just tapped the
            # level" moment.
            bull_tap = (bull_in_zone & ~bull_in_zone.shift(1).fillna(False)) | _sweep_recent("h1_bull_liquidity_sweep", 1) | _sweep_recent("m15_bull_liquidity_sweep", 1)
            bear_tap = (bear_in_zone & ~bear_in_zone.shift(1).fillna(False)) | _sweep_recent("h1_bear_liquidity_sweep", 1) | _sweep_recent("m15_bear_liquidity_sweep", 1)
            bull_tap = (bull_tap & bias_bull).fillna(False)
            bear_tap = (bear_tap & bias_bear).fillna(False)

            bull_engulf = df.get("entry_bull_engulfing", pd.Series(False, index=df.index)).fillna(False)
            bear_engulf = df.get("entry_bear_engulfing", pd.Series(False, index=df.index)).fillna(False)

            # max_gap=20 (5-min bars -> within ~100 minutes of the tap):
            # the strategy's own sequence is "tap the level, THEN wait for
            # an engulfing candle" -- a genuinely bounded reaction window,
            # own default since the source gives no exact number, chosen to
            # be short enough that the engulfing candle is still plausibly
            # reacting to that specific level tap rather than an unrelated
            # much-later candle.
            df["entry_htf_key_level_long_confirm"] = concepts.sequential_event(bull_tap, bull_engulf, max_gap=20)
            df["entry_htf_key_level_short_confirm"] = concepts.sequential_event(bear_tap, bear_engulf, max_gap=20)

        if "pdhl_mtf_reversal" in self.config.concepts_used:
            # PDH/PDL Multi-Timeframe Reversal: 15m close-beyond-PDH/PDL
            # (m15_pdhl_m15_bull_confirm_event, computed pre-merge above)
            # "arms" the setup for the REST of that UTC day (own default --
            # the source gives no exact expiry window, and PDH/PDL itself
            # only changes once a day, so day-scoped is the natural match),
            # THEN price returning to touch that level on the 5m entry
            # frame, THEN a Hammer (with the "one shot" N-consecutive-
            # approach-candles filter, Hammer only) or Bullish/Bearish
            # Engulfing (no such filter, per the strategy's own wording)
            # fires the entry.
            m15_bull_event = df.get("m15_pdhl_m15_bull_confirm_event")
            m15_bear_event = df.get("m15_pdhl_m15_bear_confirm_event")
            pdh = df.get("m15_pdh")
            pdl = df.get("m15_pdl")
            if all(x is not None for x in (m15_bull_event, m15_bear_event, pdh, pdl)):
                day_key = pd.Series(df.index.date, index=df.index)
                armed_bull = m15_bull_event.fillna(False).where(m15_bull_event.fillna(False)).groupby(day_key).ffill().fillna(False).astype(bool)
                armed_bear = m15_bear_event.fillna(False).where(m15_bear_event.fillna(False)).groupby(day_key).ffill().fillna(False).astype(bool)

                low, high = df["low"], df["high"]
                touch_pdh = ((low <= pdh) & (high >= pdh)).fillna(False)
                touch_pdl = ((low <= pdl) & (high >= pdl)).fillna(False)

                # "One shot" filter (Hammer only): the 2 candles immediately
                # before the signal candle must be same-direction as the
                # APPROACH into the level (bearish candles dropping down
                # into PDH for a long Hammer setup, bullish candles rising
                # into PDL for a short setup) with no doji among them --
                # own default N=2 (source gives no exact number), doji
                # threshold matches doji_pattern()'s own default (body <10%
                # of range).
                body = (df["close"] - df["open"]).abs()
                rng = (df["high"] - df["low"]).replace(0, float("nan"))
                body_pct = (body / rng).fillna(0.0) * 100.0
                is_doji = body_pct < 10.0
                approach_bear = ((df["close"] < df["open"]) & ~is_doji).fillna(False)
                approach_bull = ((df["close"] > df["open"]) & ~is_doji).fillna(False)
                one_shot_bull = (approach_bear.shift(1).fillna(False) & approach_bear.shift(2).fillna(False))
                one_shot_bear = (approach_bull.shift(1).fillna(False) & approach_bull.shift(2).fillna(False))

                bull_engulf = df.get("entry_bull_engulfing", pd.Series(False, index=df.index)).fillna(False)
                bear_engulf = df.get("entry_bear_engulfing", pd.Series(False, index=df.index)).fillna(False)
                bull_hammer = df.get("entry_bull_pin_bar", pd.Series(False, index=df.index)).fillna(False)
                bear_hammer = df.get("entry_bear_pin_bar", pd.Series(False, index=df.index)).fillna(False)

                long_engulf = armed_bull & touch_pdh & bull_engulf
                long_hammer = armed_bull & touch_pdh & bull_hammer & one_shot_bull
                short_engulf = armed_bear & touch_pdl & bear_engulf
                short_hammer = armed_bear & touch_pdl & bear_hammer & one_shot_bear

                df["entry_pdhl_mtf_long_confirm"] = (long_engulf | long_hammer).fillna(False)
                df["entry_pdhl_mtf_short_confirm"] = (short_engulf | short_hammer).fillna(False)
            else:
                df["entry_pdhl_mtf_long_confirm"] = pd.Series(False, index=df.index)
                df["entry_pdhl_mtf_short_confirm"] = pd.Series(False, index=df.index)

        if "cisd_entry" in self.config.concepts_used:
            # SAR + SMC (CISD Entry): CISD (Change in State of Delivery) --
            # checked first whether an existing primitive ("last opposite
            # candle before a move, retested" -- Order Block mitigation /
            # CRT invalidation shape) could be reused directly. It can't
            # quite: order_blocks() is anchored to a BOS (a swing-structure
            # break), while CISD here is anchored to a SHARP MOVE (3+
            # consecutive strong same-direction candles, a genuinely
            # different, non-structural trigger the task explicitly
            # describes) -- so this is new, but built entirely from
            # existing primitives (consolidation_impulse_zones for the 1H
            # zone, sequential_event chained twice for confirm-then-
            # retrace, same composition style already used for
            # double_choch_confirmation above).
            demand_lo, demand_hi = df.get("h1_demand_low"), df.get("h1_demand_high")
            supply_lo, supply_hi = df.get("h1_supply_low"), df.get("h1_supply_high")
            close, open_ = df["close"], df["open"]
            in_demand = ((close >= demand_lo) & (close <= demand_hi)).fillna(False) if demand_lo is not None else pd.Series(False, index=df.index)
            in_supply = ((close >= supply_lo) & (close <= supply_hi)).fillna(False) if supply_lo is not None else pd.Series(False, index=df.index)

            bullish, bearish = close > open_, close < open_
            body = (close - open_).abs()
            rng = (df["high"] - df["low"]).replace(0, float("nan"))
            body_pct = (body / rng).fillna(0.0) * 100.0
            # "Sharp" own default: body >= 50% of its own range (source
            # gives no exact ATR-multiple number), 3+ consecutive.
            strong = body_pct >= 50.0
            strong_bull = (bullish & strong).fillna(False)
            strong_bear = (bearish & strong).fillna(False)
            run3_bull = (strong_bull & strong_bull.shift(1).fillna(False) & strong_bull.shift(2).fillna(False))
            run3_bear = (strong_bear & strong_bear.shift(1).fillna(False) & strong_bear.shift(2).fillna(False))
            # The sharp move only counts if it happened while price was
            # inside the relevant 1H zone (Stage 1 -> Stage 2 ordering,
            # checked at the move's own completion bar).
            run3_bear_in_zone = (run3_bear & in_demand).fillna(False)  # sharp DOWN move in demand zone -> CISD long setup
            run3_bull_in_zone = (run3_bull & in_supply).fillna(False)  # sharp UP move in supply zone -> CISD short setup

            prior_bull_candle = (close.shift(3) > open_.shift(3)).fillna(False)
            prior_bear_candle = (close.shift(3) < open_.shift(3)).fillna(False)
            cisd_long_trigger = run3_bear_in_zone & prior_bull_candle
            cisd_short_trigger = run3_bull_in_zone & prior_bear_candle
            cisd_long_level = close.shift(3).where(cisd_long_trigger).ffill()
            cisd_short_level = close.shift(3).where(cisd_short_trigger).ffill()

            # Stage 4: a LATER candle CLOSES back across the CISD line.
            # max_gap=15 (own default, ~75 min on 5m bars): the source
            # gives no exact reaction window, bounded so a stale CISD level
            # from long ago can't pair with an unrelated much-later close.
            close_above_cisd = (close > cisd_long_level).fillna(False)
            close_below_cisd = (close < cisd_short_level).fillna(False)
            cisd_long_confirm_event = concepts.sequential_event(cisd_long_trigger, close_above_cisd, max_gap=15)
            cisd_short_confirm_event = concepts.sequential_event(cisd_short_trigger, close_below_cisd, max_gap=15)

            # Stage 5: price RETRACES back to touch the CISD line, strictly
            # after the confirmation -- max_gap=30 (~150 min), own default.
            touch_cisd_long = ((df["low"] <= cisd_long_level) & (df["high"] >= cisd_long_level)).fillna(False)
            touch_cisd_short = ((df["low"] <= cisd_short_level) & (df["high"] >= cisd_short_level)).fillna(False)
            df["entry_cisd_long_confirm"] = concepts.sequential_event(cisd_long_confirm_event, touch_cisd_long, max_gap=30)
            df["entry_cisd_short_confirm"] = concepts.sequential_event(cisd_short_confirm_event, touch_cisd_short, max_gap=30)

        if "fractal_sweep_reversal" in self.config.concepts_used:
            # 4H Fractal Sweep Reversal: the strategy's own rules say to use
            # level_sweep_reclaim() directly -- but that primitive derives
            # its level from the SAME frame it's called on, and this
            # strategy needs the level from the 4H role while the sweep/
            # reclaim EVENT is checked on the 5m entry frame. This is
            # level_sweep_reclaim()'s exact formula, copied against the
            # merged h4_support/h4_resistance columns instead (same
            # already-established pattern as pdhl_reversal/liquidity_sweep_
            # reclaim above, which do the identical thing for their own
            # non-generic level sources).
            h4_support, h4_resistance = df.get("h4_support"), df.get("h4_resistance")
            if h4_support is not None and h4_resistance is not None:
                low, high, close = df["low"], df["high"], df["close"]
                body = (df["close"] - df["open"]).abs()
                rng = (df["high"] - df["low"]).replace(0, float("nan"))
                body_pct = (body / rng).fillna(0.0) * 100.0
                # "Strong candle" filter (own default 50%, no exact number
                # given): applied to the SWEEP candle itself (gating the
                # sweep event before it's allowed to pair with a later
                # reclaim), exactly matching the strategy's own wording --
                # excludes sweeps made of small-body/doji-like candles.
                strong = body_pct >= 50.0
                bull_sweep = ((low < h4_support) & strong).fillna(False)
                bear_sweep = ((high > h4_resistance) & strong).fillna(False)
                was_below = (close.shift(1) <= h4_support.shift(1)).fillna(False)
                was_above = (close.shift(1) >= h4_resistance.shift(1)).fillna(False)
                bull_reclaim = ((close > h4_support) & was_below).fillna(False)
                bear_reclaim = ((close < h4_resistance) & was_above).fillna(False)
                df["entry_fractal_sweep_long_confirm"] = concepts.sequential_event(bull_sweep, bull_reclaim, max_gap=20)
                df["entry_fractal_sweep_short_confirm"] = concepts.sequential_event(bear_sweep, bear_reclaim, max_gap=20)
            else:
                df["entry_fractal_sweep_long_confirm"] = pd.Series(False, index=df.index)
                df["entry_fractal_sweep_short_confirm"] = pd.Series(False, index=df.index)

        if "liquidity_sweep_multi_confirm" in self.config.concepts_used:
            # Liquidity Sweep Multi-Confirmation: bias-role sweep already
            # confirmed pre-merge (bias_sweep_confirmed_bull/bear, forward-
            # filled across every entry-TF bar belonging to that bias bar --
            # a genuine "armed" state, not re-derived here). CISD path
            # (default/primary mode; the FVG path is explicitly out of
            # scope for v1, per the strategy's own wording): the "last
            # opposite-candle-close line" is the most recent bearish (for
            # a long setup)/bullish (for a short setup) entry-TF candle
            # seen WHILE the bias sweep is armed -- continually refreshed
            # via where().ffill(), same technique as the existing CISD
            # entry's cisd_long_level/cisd_short_level. Entry fires on the
            # bar price genuinely CROSSES that line (edge-triggered, not
            # "is currently above it" -- same containment-bug fix applied
            # throughout this session), gated to only while still armed.
            bias_armed_bull = df.get("bias_sweep_confirmed_bull", pd.Series(False, index=df.index)).fillna(False)
            bias_armed_bear = df.get("bias_sweep_confirmed_bear", pd.Series(False, index=df.index)).fillna(False)
            close, open_ = df["close"], df["open"]
            bullish_c, bearish_c = close > open_, close < open_
            cisd_long_level = close.where(bearish_c & bias_armed_bull).ffill()
            cisd_short_level = close.where(bullish_c & bias_armed_bear).ffill()
            cross_above = ((close > cisd_long_level) & ~(close.shift(1) > cisd_long_level.shift(1))).fillna(False)
            cross_below = ((close < cisd_short_level) & ~(close.shift(1) < cisd_short_level.shift(1))).fillna(False)
            df["entry_liqsweep_multi_long_confirm"] = (cross_above & bias_armed_bull).fillna(False)
            df["entry_liqsweep_multi_short_confirm"] = (cross_below & bias_armed_bear).fillna(False)

        if "liquidity_sweep_cisd_swing" in self.config.concepts_used:
            # Liquidity Sweep + CISD (Pure Swing Variant): identical CISD
            # mechanics to the existing SAR+SMC (CISD Entry) strategy's
            # stages 3-5 (last opposite candle -> line -> confirm close ->
            # retrace touch, chained sequential_event()s), reused directly
            # -- the only thing that changes is the TRIGGER anchoring the
            # CISD line: a bias-role (pure swing, 1H default) liquidity
            # sweep event instead of cisd_entry's "3-candle sharp move
            # inside a demand/supply zone." Built as the 1H bias -> 5m entry
            # pairing (the task's own default/primary option); the
            # alternative 4H bias -> 15m entry pairing is architecturally
            # identical (same code, different timeframes_by_role) and was
            # not separately backtested for v1, to keep this batch's scope
            # to 3 base strategies -- flagged, not silently skipped.
            bias_bull_sweep = df.get("bias_bull_liquidity_sweep", pd.Series(False, index=df.index)).fillna(False)
            bias_bear_sweep = df.get("bias_bear_liquidity_sweep", pd.Series(False, index=df.index)).fillna(False)
            bull_sweep_event = (bias_bull_sweep & ~bias_bull_sweep.shift(1).fillna(False))
            bear_sweep_event = (bias_bear_sweep & ~bias_bear_sweep.shift(1).fillna(False))
            close, open_ = df["close"], df["open"]
            bullish_c, bearish_c = close > open_, close < open_
            cisd_long_trigger = (bearish_c.shift(1).fillna(False) & bull_sweep_event)
            cisd_short_trigger = (bullish_c.shift(1).fillna(False) & bear_sweep_event)
            cisd_long_level = close.shift(1).where(cisd_long_trigger).ffill()
            cisd_short_level = close.shift(1).where(cisd_short_trigger).ffill()
            # max_gap=15/30 (own defaults, same 5m-bar reasoning as the
            # existing cisd_entry strategy): the source gives no exact
            # confirm/retrace reaction window for either stage.
            close_above_cisd = (close > cisd_long_level).fillna(False)
            close_below_cisd = (close < cisd_short_level).fillna(False)
            cisd_long_confirm_event = concepts.sequential_event(cisd_long_trigger, close_above_cisd, max_gap=15)
            cisd_short_confirm_event = concepts.sequential_event(cisd_short_trigger, close_below_cisd, max_gap=15)
            touch_cisd_long = ((df["low"] <= cisd_long_level) & (df["high"] >= cisd_long_level)).fillna(False)
            touch_cisd_short = ((df["low"] <= cisd_short_level) & (df["high"] >= cisd_short_level)).fillna(False)
            df["entry_liqsweep_cisd_long_confirm"] = concepts.sequential_event(cisd_long_confirm_event, touch_cisd_long, max_gap=30)
            df["entry_liqsweep_cisd_short_confirm"] = concepts.sequential_event(cisd_short_confirm_event, touch_cisd_short, max_gap=30)

        _sweep_engulf_used = {"liquidity_sweep_engulfing_loose", "liquidity_sweep_engulfing_strict"} & set(self.config.concepts_used)
        if _sweep_engulf_used:
            # New Batch 5, Strategy 1: "the 4H sweep MUST occur before the
            # 5M engulfing pattern is checked" -- bias_support/
            # bias_resistance (the 4H swing level, already causally merged
            # onto this 5m entry frame) checked against the entry frame's
            # own low/high/close, then ordered against the entry role's own
            # engulfing pattern (entry_bull_engulfing/entry_bear_engulfing,
            # already computed by _compute_concept_columns since "engulfing"
            # is required alongside this concept -- body-only, per
            # concepts.engulfing_candle()'s own docstring) via
            # sequential_event(). LOOSE: any sweep (a wick beyond the level,
            # OR a body close through it) counts -- support/resistance
            # comparison alone. STRICT: only concepts.liquidity_sweep()'s
            # own same-bar wick-beyond-then-close-back-inside formula counts
            # (source's own wording for the strict variant), applied against
            # the merged 4H level instead of a same-frame swing (same
            # technique as fractal_sweep_reversal's h4_support/h4_resistance
            # copy above).
            bias_support = df.get("bias_support")
            bias_resistance = df.get("bias_resistance")
            bull_engulf = df.get("entry_bull_engulfing")
            bear_engulf = df.get("entry_bear_engulfing")
            if bias_support is not None and bias_resistance is not None and bull_engulf is not None:
                low, high, close = df["low"], df["high"], df["close"]
                if "liquidity_sweep_engulfing_strict" in _sweep_engulf_used:
                    bull_sweep = ((low < bias_support) & (close >= bias_support)).fillna(False)
                    bear_sweep = ((high > bias_resistance) & (close <= bias_resistance)).fillna(False)
                else:
                    bull_sweep = (low < bias_support).fillna(False)
                    bear_sweep = (high > bias_resistance).fillna(False)
                # max_gap=60 5m bars (~5 hours, roughly one 4H bar's length):
                # own default -- the source mandates the ordering but gives
                # no exact reaction window between the sweep and the
                # engulfing candle forming.
                df["entry_liqsweep_engulf_long_confirm"] = concepts.sequential_event(bull_sweep, bull_engulf, max_gap=60)
                df["entry_liqsweep_engulf_short_confirm"] = concepts.sequential_event(bear_sweep, bear_engulf, max_gap=60)
                # Stop-loss anchor: "below/above the low/high of the sweep
                # candle" (source, explicit) -- held (ffilled) from the
                # sweep bar until the entry that follows it consumes it.
                df["entry_liqsweep_engulf_sl_bull"] = low.where(bull_sweep).ffill()
                df["entry_liqsweep_engulf_sl_bear"] = high.where(bear_sweep).ffill()
            else:
                df["entry_liqsweep_engulf_long_confirm"] = pd.Series(False, index=df.index)
                df["entry_liqsweep_engulf_short_confirm"] = pd.Series(False, index=df.index)

        if "ote_liquidity_sweep_reversal" in self.config.concepts_used:
            # OTE Liquidity Sweep Reversal: the ONE genuinely new formula
            # this batch adds -- a plain, deterministic 62%-79% Fibonacci
            # retracement zone from the bias role's most recent confirmed
            # swing high/low (bias_support/bias_resistance, already
            # forward-filled swing levels -- the same "external high/low"
            # approximation fractal_sweep_reversal already made for its own
            # "fractal levels"). Mirror-logic for longs (uptrend) since the
            # source only detailed the short/downtrend case explicitly --
            # flagged per the task's own instruction. Local sweep + later-
            # candle "acceptance" close inside the zone reuses
            # level_sweep_reclaim() UNMODIFIED, called directly against the
            # entry TF's own OHLC (its internal support_resistance() call is
            # the "local high/low inside/near the zone" the strategy's own
            # wording asks for) -- gated to only count when it happens
            # shortly after price arrives in the OTE zone. The mandatory
            # "skip the trade entirely if RR < 3" hard filter is NOT new
            # code here -- it's the existing generic min_risk_reward_filter
            # / risk_reward_filter_uses_take_profit mechanism (already used
            # by SAR+SMC's own baseline config), set directly on this
            # strategy's base config instead of only as an optimizer
            # variant, since the task requires it as a hard v1 rule, not an
            # optional strictness upgrade.
            bias_trend = df.get("bias_structure_trend")
            bias_support, bias_resistance = df.get("bias_support"), df.get("bias_resistance")
            if bias_trend is not None and bias_support is not None and bias_resistance is not None:
                uptrend = (bias_trend == "up")
                downtrend = (bias_trend == "down")
                fib_range = (bias_resistance - bias_support)
                ote_low_up = bias_resistance - fib_range * 0.79
                ote_high_up = bias_resistance - fib_range * 0.618
                ote_low_dn = bias_support + fib_range * 0.618
                ote_high_dn = bias_support + fib_range * 0.79
                close = df["close"]
                in_ote_long = (uptrend & (close >= ote_low_up) & (close <= ote_high_up)).fillna(False)
                in_ote_short = (downtrend & (close >= ote_low_dn) & (close <= ote_high_dn)).fillna(False)
                zone_tap_long = (in_ote_long & ~in_ote_long.shift(1).fillna(False)).fillna(False)
                zone_tap_short = (in_ote_short & ~in_ote_short.shift(1).fillna(False)).fillna(False)
                bull_sweep, bear_sweep, bull_reclaim, bear_reclaim = concepts.level_sweep_reclaim(df)
                # max_gap=10 (entry TF, 15m default -> ~150 min per stage):
                # own default, source gives no exact reaction window for
                # either "sweep after tapping the zone" or the acceptance
                # close that follows it.
                sweep_after_tap_long = concepts.sequential_event(zone_tap_long, bull_sweep, max_gap=10)
                sweep_after_tap_short = concepts.sequential_event(zone_tap_short, bear_sweep, max_gap=10)
                df["entry_ote_long_confirm"] = concepts.sequential_event(sweep_after_tap_long, bull_reclaim, max_gap=10)
                df["entry_ote_short_confirm"] = concepts.sequential_event(sweep_after_tap_short, bear_reclaim, max_gap=10)
            else:
                df["entry_ote_long_confirm"] = pd.Series(False, index=df.index)
                df["entry_ote_short_confirm"] = pd.Series(False, index=df.index)

        if "trendline_breakout" in self.config.concepts_used:
            # New Batch 3, Strategy 1 (HTF Trend Trendline Breakout): the
            # entry-TF trendline break (computed pre-merge above) gated by
            # BOTH the 4H and 1H roles' own confirmed structural trend --
            # "trend must be confirmed on both" -- only computable HERE,
            # post-merge, since it reads two different non-entry roles'
            # columns together on the same (entry) frame.
            h4_trend = df.get("h4_structure_trend")
            h1_trend = df.get("h1_structure_trend")
            bull_break = df.get("entry_bull_trendline_break", pd.Series(False, index=df.index)).fillna(False)
            bear_break = df.get("entry_bear_trendline_break", pd.Series(False, index=df.index)).fillna(False)
            if h4_trend is not None and h1_trend is not None:
                htf_up = (h4_trend == "up") & (h1_trend == "up")
                htf_down = (h4_trend == "down") & (h1_trend == "down")
            else:
                htf_up = pd.Series(False, index=df.index)
                htf_down = pd.Series(False, index=df.index)
            df["entry_trendline_long_confirm"] = (bull_break & htf_up).fillna(False)
            df["entry_trendline_short_confirm"] = (bear_break & htf_down).fillna(False)

            # Optional soft filters (source says "reduce position size", not
            # skip -- own default halving, 0.5x, since no exact number is
            # given): a calendar weekend, OR the 1H role currently showing a
            # "sideways" regime. Read by on_bar() at the signal bar to set
            # Signal.risk_multiplier -- never a hard skip.
            weekday = concepts.day_of_week_column(df)
            is_weekend = weekday.isin(["saturday", "sunday"])
            h1_regime = df.get("h1_trend_regime")
            is_h1_sideways = (h1_regime == "sideways") if h1_regime is not None else pd.Series(False, index=df.index)
            df["entry_trendline_soft_reduce"] = (is_weekend | is_h1_sideways).fillna(False)

        if "htf_ltf_fvg_ob_confluence" in self.config.concepts_used:
            # New Batch 3, Strategy 3 (HTF-LTF FVG/OB Confluence Entry):
            # only computable post-merge -- reads the bias (4H) role's
            # trend/OB-validity/FVG columns together with the entry (15m)
            # role's own trend and FVG columns, on the same (entry) frame.
            bias_trend = df.get("bias_trend_regime")
            ltf_trend = df.get("entry_trend_regime")
            bias_bull_ob_valid = df.get("bias_bull_ob_valid")
            bias_bear_ob_valid = df.get("bias_bear_ob_valid")
            bias_fvg_bull_low = df.get("bias_fvg_bull_low")
            bias_fvg_bear_high = df.get("bias_fvg_bear_high")

            zeros = pd.Series(False, index=df.index)
            matching_zone_bull = (
                (bias_bull_ob_valid.fillna(False) if bias_bull_ob_valid is not None else zeros)
                | (bias_fvg_bull_low.notna() if bias_fvg_bull_low is not None else zeros)
            )
            matching_zone_bear = (
                (bias_bear_ob_valid.fillna(False) if bias_bear_ob_valid is not None else zeros)
                | (bias_fvg_bear_high.notna() if bias_fvg_bear_high is not None else zeros)
            )

            htf_bullish = (bias_trend == "up") if bias_trend is not None else zeros
            htf_bearish = (bias_trend == "down") if bias_trend is not None else zeros
            ltf_bullish = (ltf_trend == "up") if ltf_trend is not None else zeros
            ltf_bearish = (ltf_trend == "down") if ltf_trend is not None else zeros

            # HARD FILTER (High Probability Zone): HTF and LTF trend must
            # match; an unclear/sideways HTF (bias_trend not "up"/"down" at
            # all) can never satisfy either side, so it is excluded
            # automatically -- no separate "don't trade if HTF sideways"
            # check is needed beyond this.
            high_prob_bull = (htf_bullish & ltf_bullish & matching_zone_bull).fillna(False)
            high_prob_bear = (htf_bearish & ltf_bearish & matching_zone_bear).fillna(False)

            fvg_bull_low, fvg_bull_high = df.get("entry_fvg_bull_low"), df.get("entry_fvg_bull_high")
            fvg_bear_low, fvg_bear_high = df.get("entry_fvg_bear_low"), df.get("entry_fvg_bear_high")
            low, high = df["low"], df["high"]

            if fvg_bull_low is not None and fvg_bull_high is not None:
                fvg_bull_mid = (fvg_bull_low + fvg_bull_high) / 2.0
                # Entry: a retracement TOUCH of the zone (wick reaching it,
                # not necessarily closing inside) -- edge-triggered arrival,
                # first_signal_per_level() enforcing one trade per distinct
                # gap (same "once-tested" pattern fvg_reversal/DMC already
                # use). Own default simplification: the source describes a
                # hierarchy (50% level preferred, full-zone touch as a
                # fallback if 50% is never reached) -- since a full-zone
                # touch always chronologically precedes or coincides with a
                # 50% touch (the near edge must be crossed first) and only
                # ONE trade is taken per gap either way, this is
                # representable as a single first-touch-of-zone event: a
                # candle whose range reaches all the way to the 50% level
                # (the common case) has satisfied the "primary" definition;
                # one that only tags the near edge has satisfied the
                # "fallback" definition -- without needing two separate,
                # lookahead-dependent trigger mechanisms for what the source
                # itself treats as one hierarchy, not two independent rules.
                touch_zone_bull = ((low <= fvg_bull_high) & (high >= fvg_bull_low)).fillna(False)
                first_touch_bull = (touch_zone_bull & ~touch_zone_bull.shift(1).fillna(False))
                raw_bull_event = concepts.first_signal_per_level(first_touch_bull, fvg_bull_low)
            else:
                fvg_bull_mid = pd.Series(float("nan"), index=df.index)
                raw_bull_event = zeros

            if fvg_bear_low is not None and fvg_bear_high is not None:
                fvg_bear_mid = (fvg_bear_low + fvg_bear_high) / 2.0
                touch_zone_bear = ((low <= fvg_bear_high) & (high >= fvg_bear_low)).fillna(False)
                first_touch_bear = (touch_zone_bear & ~touch_zone_bear.shift(1).fillna(False))
                raw_bear_event = concepts.first_signal_per_level(first_touch_bear, fvg_bear_high)
            else:
                fvg_bear_mid = pd.Series(float("nan"), index=df.index)
                raw_bear_event = zeros

            df["entry_confluence_long_confirm"] = (raw_bull_event & high_prob_bull).fillna(False)
            df["entry_confluence_short_confirm"] = (raw_bear_event & high_prob_bear).fillna(False)

            # Stop-loss refinement: "if the FVG-producing candle is
            # unusually large, place the stop at its 50% level instead" --
            # the FVG-producing/impulse candle is bar i-1 relative to the
            # gap's own confirmation bar i (the classic 3-candle FVG shape:
            # the gap sits between candle i-2's high/low and candle i's
            # low/high, with i-1 the impulsive move between them). "Unusual"
            # -- own default, source gives no exact number -- reuses the
            # same 1.5x ATR(14) large-candle threshold already used
            # elsewhere in this batch (range_breakout_volume_confirm) and
            # this codebase (consolidation_impulse_zones' impulse_atr_mult
            # default). Mostly-NaN sparse columns inserted at the FRONT of
            # _compute_stop_loss()'s existing structure-SL candidate chain
            # below -- when NOT large, that chain already falls through to
            # the plain entry_fvg_bull_low/entry_fvg_bear_high zone edge
            # (already a candidate there), giving "slightly beyond the FVG
            # zone" for free with no new column needed for that case.
            if fvg_bull_low is not None:
                atr14 = df.get("entry_atr_14")
                if atr14 is None:
                    atr14 = concepts.atr(df, 14)
                origin_range_bull = (df["high"].shift(1) - df["low"].shift(1))
                gap_formed_bull = (fvg_bull_low != fvg_bull_low.shift(1)) & fvg_bull_low.notna()
                origin_range_at_formation_bull = origin_range_bull.where(gap_formed_bull).ffill()
                is_large_bull = (origin_range_at_formation_bull >= 1.5 * atr14).fillna(False)
                df["entry_confluence_sl_bull"] = fvg_bull_mid.where(is_large_bull)
            if fvg_bear_high is not None:
                atr14 = df.get("entry_atr_14")
                if atr14 is None:
                    atr14 = concepts.atr(df, 14)
                origin_range_bear = (df["high"].shift(1) - df["low"].shift(1))
                gap_formed_bear = (fvg_bear_high != fvg_bear_high.shift(1)) & fvg_bear_high.notna()
                origin_range_at_formation_bear = origin_range_bear.where(gap_formed_bear).ffill()
                is_large_bear = (origin_range_at_formation_bear >= 1.5 * atr14).fillna(False)
                df["entry_confluence_sl_bear"] = fvg_bear_mid.where(is_large_bear)

        if "heikin_ashi_reversal" in self.config.concepts_used:
            # New Batch 4, Strategy 1: the bias(1H)-role HA reversal zone
            # (computed pre-merge above) touched by the entry(15m) role's
            # OWN real candles -- "wait for price to return to the HA
            # candles," ATR-buffered "near" -- only computable HERE, post-
            # merge, since it reads the merged bias_ha_zone_* columns
            # together with entry-frame close.
            bull_zone_low = df.get("bias_ha_zone_low")
            bull_zone_high = df.get("bias_ha_zone_high")
            bear_zone_low = df.get("bias_ha_bear_zone_low")
            bear_zone_high = df.get("bias_ha_bear_zone_high")
            bias_atr = df.get("bias_atr_14")
            close = df["close"]
            zeros = pd.Series(False, index=df.index)
            if bull_zone_low is not None and bias_atr is not None:
                buffer = 0.5 * bias_atr
                lo, hi = bull_zone_low - buffer, bull_zone_high + buffer
                in_zone = ((close >= lo) & (close <= hi)).fillna(False)
                tag = (in_zone & ~in_zone.shift(1).fillna(False)).fillna(False)
                df["entry_ha_long_confirm"] = concepts.first_signal_per_level(tag, bull_zone_low)
                df["entry_ha_sl_bull"] = bull_zone_low
            else:
                df["entry_ha_long_confirm"] = zeros
            if bear_zone_low is not None and bias_atr is not None:
                buffer = 0.5 * bias_atr
                lo, hi = bear_zone_low - buffer, bear_zone_high + buffer
                in_zone = ((close >= lo) & (close <= hi)).fillna(False)
                tag = (in_zone & ~in_zone.shift(1).fillna(False)).fillna(False)
                df["entry_ha_short_confirm"] = concepts.first_signal_per_level(tag, bear_zone_low)
                df["entry_ha_sl_bear"] = bear_zone_high
            else:
                df["entry_ha_short_confirm"] = zeros

        if "donchian_lwti_volume_confluence" in self.config.concepts_used:
            # New Batch 4, Strategy 5: all 3 legs required (AND), source's
            # own hard filter -- "if Donchian breaks out but LWTI or Volume
            # do not confirm, skip the trade entirely." The bias(1H)
            # breakout is a discrete, sparse event once merged onto the
            # entry(15m) frame (True only for the entry bars inside that
            # exact 1H bar) -- extended forward for a short window (8 entry
            # bars ~= 2 hours, own default) so the LWTI/Volume legs have a
            # real chance to confirm on a LATER entry-tf bar within the
            # same breakout, not only the single bar it first appears on.
            bias_bull_break = df.get("bias_donchian_bull_break")
            bias_bear_break = df.get("bias_donchian_bear_break")
            lwti = df.get("entry_lwti")
            vol_ma = df.get("entry_volume_ma_30")
            zeros = pd.Series(False, index=df.index)
            if bias_bull_break is not None and lwti is not None and vol_ma is not None:
                def _extend(event, limit=8):
                    marker = pd.Series(np.where(event.fillna(False).values, 1.0, np.nan), index=event.index)
                    return marker.ffill(limit=limit).fillna(0).astype(bool)
                bull_break_active = _extend(bias_bull_break)
                bear_break_active = _extend(bias_bear_break)
                vol_ok = (df["volume"] > vol_ma).fillna(False)
                df["entry_donchian_long_confirm"] = (bull_break_active & (lwti > 50) & vol_ok).fillna(False)
                df["entry_donchian_short_confirm"] = (bear_break_active & (lwti < -50) & vol_ok).fillna(False)
            else:
                df["entry_donchian_long_confirm"] = zeros
                df["entry_donchian_short_confirm"] = zeros

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
            # Branching/conditional entry logic (entry_rule_groups: N
            # independent alternative entry paths, e.g. "P-shape enters
            # this way, B-shape enters that way, D-shape enters a third
            # way") takes priority over everything else whenever populated
            # -- it's strictly more expressive than long/short (which is
            # itself just a 2-group special case), so a strategy using it
            # should have entry_conditions/long_entry_conditions/
            # short_entry_conditions left empty.
            if cfg.entry_rule_groups:
                direction, matched_conditions = self._eval_rule_groups(df, i)
                entry_ok = direction is not None
            # Two mutually-exclusive rule sets (a strategy with separate
            # "Long Entry Rules"/"Short Entry Rules" sections) take priority
            # over the legacy single entry_conditions gate whenever either is
            # populated. A strategy that only ever fills entry_conditions
            # (every strategy saved before this feature existed) falls
            # through to the unchanged legacy branch below.
            elif cfg.long_entry_conditions or cfg.short_entry_conditions:
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

            # (Batch 2, Task 2) Pre-trade discard filters -- a signal that
            # otherwise fires is thrown away entirely (no trade, not a
            # different SL/TP) when it fails either check. Both no-ops
            # unless explicitly configured, so every strategy saved before
            # this feature exists is completely unaffected.
            if cfg.sl_distance_filter_pct and sl is not None and price:
                sl_distance_pct = abs(price - sl) / price * 100.0
                min_pct = cfg.sl_distance_filter_pct.get("min_pct")
                max_pct = cfg.sl_distance_filter_pct.get("max_pct")
                if (min_pct is not None and sl_distance_pct < min_pct) or \
                   (max_pct is not None and sl_distance_pct > max_pct):
                    return None
            if cfg.min_risk_reward_filter is not None and sl is not None:
                # Two mutually-exclusive reference points for the same
                # filter: risk_reward_filter_uses_take_profit checks R:R
                # against the EXACT level the trade will actually exit at
                # (tp, already computed above) -- for strategies whose own
                # source says the filter and the real target are the same
                # thing. primary_target_lookback_bars (the older path) is
                # for strategies that explicitly describe a DIFFERENT,
                # nearer reference for the filter than the actual take-
                # profit. Using the wrong one silently lets a trade pass a
                # 2.5:1-looking filter check while actually exiting much
                # closer than that -- confirmed against real Supply/Demand
                # Zone Strategy trade data before this fix.
                if cfg.risk_reward_filter_uses_take_profit:
                    filter_target = tp
                elif cfg.primary_target_lookback_bars:
                    filter_target = self._compute_primary_target(df, i, direction, cfg.primary_target_lookback_bars)
                else:
                    filter_target = None
                if filter_target is not None:
                    risk = abs(price - sl)
                    if risk == 0:
                        return None
                    filter_rr = abs(filter_target - price) / risk
                    if filter_rr < cfg.min_risk_reward_filter:
                        return None
                elif cfg.risk_reward_filter_uses_take_profit or cfg.primary_target_lookback_bars:
                    # A reference mode was explicitly requested but produced
                    # no usable level on this bar (e.g. no structural zone
                    # found yet) -- can't verify the filter, so don't take
                    # the trade rather than silently skip the check.
                    return None

            action = "buy" if direction == "bullish" else "sell"
            # New Batch 3, Strategy 1's optional soft size-reduction filter
            # (weekend / 1H-sideways -- see the "trendline_breakout"
            # composite block in prepare()): reads the per-bar flag it
            # already computed there. None for every other strategy (the
            # column simply doesn't exist), so Signal.risk_multiplier stays
            # None -- full size, byte-for-byte unchanged.
            risk_multiplier = None
            if self.config.concepts_used and "trendline_breakout" in self.config.concepts_used:
                soft_reduce = self._get(df, i, "entry_trendline_soft_reduce")
                if soft_reduce:
                    risk_multiplier = 0.5
            return Signal(action=action, stop_loss=sl, take_profit=tp, reason=self._describe(matched_conditions),
                          risk_multiplier=risk_multiplier)

        else:
            # Direction-aware exit gate: a condition with exit_direction set
            # only applies while the open position matches that side (see
            # Condition.exit_direction's docstring). None (every strategy
            # saved before this existed) still applies to both sides,
            # unchanged -- `applicable` then equals cfg.exit_conditions
            # exactly like the old unconditional `all(...)` did. If EVERY
            # exit_conditions entry is direction-specific and none match
            # this position's side, there's simply nothing to check this
            # bar (falls through to the engine's own stop_loss/take_profit
            # forced-exit check instead) rather than incorrectly firing an
            # opposite-side rule or incorrectly blocking exit forever.
            if cfg.exit_conditions:
                position_direction = "bullish" if position["side"] == "long" else "bearish"
                applicable = [c for c in cfg.exit_conditions
                              if c.exit_direction is None or c.exit_direction == position_direction]
                if applicable and all(self._eval_traced(c, df, i) for c in applicable):
                    return Signal(action="exit", reason=self._describe(applicable))
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

    def _eval_rule_groups(self, df, i):
        """Returns (direction, matched_conditions) for the FIRST alternative
        entry-path group (in declared order) whose conditions are all true
        on this bar, or (None, None) if none match -- or if groups from
        BOTH directions somehow match the same bar (a genuinely
        contradictory bar), treated as no signal rather than an arbitrary
        guess about which one to take, exactly like _eval_long_short."""
        matched_bullish, matched_short = None, None
        for group in self.config.entry_rule_groups:
            conditions = group.get("conditions") or []
            if not conditions:
                continue
            if not all(self._eval_traced(c, df, i) for c in conditions):
                continue
            direction = group.get("direction")
            if direction == "bullish" and matched_bullish is None:
                matched_bullish = group
            elif direction == "bearish" and matched_short is None:
                matched_short = group
        if matched_bullish and matched_short:
            return None, None
        matched = matched_bullish or matched_short
        if matched is None:
            return None, None
        return matched["direction"], matched["conditions"]

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
        if indicator_name in ("ema", "sma", "rsi", "atr", "highest_high", "lowest_low"):
            return f"{role}_{indicator_name}_{resolved_period}"
        if indicator_name == "macd":
            # prepare_context() writes macd as SUFFIXED columns
            # (macd_line_{fast}_{slow}_{signal} etc, so several macd
            # settings can coexist on one role), but this returned a bare
            # "{role}_macd" that no frame ever contains -- so an
            # indicator_compare on macd (which the Strategy Wizard openly
            # offers, macd being in validator._PARAMETERIZED_INDICATORS)
            # read a non-existent column and evaluated False forever. Same
            # declared-but-unreadable bug class as the original VWAP and
            # MACD-wiring gaps (tracker #1 and #4), one layer further up.
            # Measured before this fix on 8441 real BTCUSDT 5m bars:
            # "macd > 0" fired 0 times while the real macd line was above
            # zero on 4516 of them. "macd" as a comparable value means the
            # MACD LINE, matching how every charting tool plots it.
            fast, slow, sig = params.get("fast"), params.get("slow"), params.get("signal")
            for ind in self.config.indicators:
                if ind["name"] != "macd":
                    continue
                if cond_role and (ind.get("role") or "entry") != cond_role:
                    continue
                p = ind["params"]
                fast = fast if fast is not None else p.get("fast")
                slow = slow if slow is not None else p.get("slow")
                sig = sig if sig is not None else p.get("signal")
                break
            # Same 12/26/9 defaults prepare_context() applies.
            return f"{role}_macd_line_{fast or 12}_{slow or 26}_{sig or 9}"
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
                # Bug fix: a role-tagged concept column merged onto the
                # entry index via MultiTimeframeContext (see mtf_context.py)
                # is NaN, not False, for every entry bar before that role's
                # FIRST higher-timeframe bar has even closed yet (merge_asof
                # simply has nothing to match against there). Merging
                # introduces this NaN into what started as a plain boolean
                # column, upcasting it to float/object -- and a bare
                # `.any()` on that array treats NaN as truthy (NaN != 0),
                # not falsy, spuriously firing a "concept happened" signal
                # in the first few bars of a backtest purely because no data
                # existed yet, before any real trigger condition could
                # possibly have occurred. Confirmed live: Laxman Rekha's
                # short_tf-role short entries opened trades at bar 0-2 of a
                # BTCUSDT backtest with short_tf_laxman_trigger_high still
                # NaN (no 15m bar had closed yet), and only skipped a real
                # stop-loss (falling through to the emergency %-fallback)
                # because THAT lookup correctly uses _get()'s pd.isna()
                # check instead of raw truthiness. `== True` instead of
                # bare truthiness correctly excludes NaN (NaN == True is
                # False, for both float and object dtypes) while leaving
                # every genuine True value unaffected -- byte-for-byte
                # unchanged for the (very common) case of a plain bool
                # array with no NaN in it at all.
                return bool((arr[start:i + 1] == True).any())  # noqa: E712

            if cond.name in ("macd_signal_cross", "macd_zero_cross"):
                # Dynamic column name (depends on cond.params, unlike every
                # other entry in event_colmap below which is static) --
                # must match exactly how prepare_context()'s indicator loop
                # named these columns for the same fast/slow/signal.
                fast = cond.params.get("fast", 12)
                slow = cond.params.get("slow", 26)
                sig = cond.params.get("signal", 9)
                suffix = f"{fast}_{slow}_{sig}"
                kind = "signal_cross" if cond.name == "macd_signal_cross" else "zero_cross"
                bull_col = _rcol(f"macd_bull_{kind}_{suffix}")
                bear_col = _rcol(f"macd_bear_{kind}_{suffix}")
                if cond.direction == "bearish":
                    return _within(bear_col)
                if cond.direction == "bullish":
                    return _within(bull_col)
                return _within(bull_col) or _within(bear_col)
            if cond.name == "sweep_invalidation_state":
                # Direct state read, no _within() window -- like
                # valid_structure_trend, this is already a per-bar STATE
                # (stays True across many bars until the opposite event
                # flips it), not a momentary event to look back for.
                if cond.direction == "bullish":
                    return bool(self._get(df, i, _rcol("long_setup_active")))
                if cond.direction == "bearish":
                    return bool(self._get(df, i, _rcol("short_setup_active")))
                return False
            if cond.name == "fvg_zone":
                # Edge-triggered re-entry ("execution: enter WHEN price
                # RETURNS to this zone" -- a discrete arrival event, not
                # "is currently inside"), unlike demand_zone/supply_zone
                # below which deliberately use plain containment (that
                # design fit multi-touch demand/supply zones fine). Plain
                # containment here fired on EVERY bar price sat inside the
                # zone -- confirmed against a real 5-symbol smoke test:
                # 2700-4400 trades per symbol with a near-total (97-99%)
                # drawdown, because a fresh trade re-opened almost every
                # single bar the state gates (sweep_invalidation_state,
                # valid_structure_trend) stayed true, each one immediately
                # eaten by commission+slippage against CRT 2.0's tight
                # 0.15% stop. Firing only on the bar price transitions from
                # outside to inside matches the source's own "returns to"
                # wording and fixes the re-entry storm at its root.
                lo_col = _rcol("fvg_bear_low" if cond.direction == "bearish" else "fvg_bull_low")
                hi_col = _rcol("fvg_bear_high" if cond.direction == "bearish" else "fvg_bull_high")
                price = self._get(df, i, "close")
                lo = self._get(df, i, lo_col)
                hi = self._get(df, i, hi_col)
                if price is None or lo is None or hi is None:
                    return False
                if not (lo <= price <= hi):
                    return False
                if i == 0:
                    return True
                prev_price = self._get(df, i - 1, "close")
                prev_lo = self._get(df, i - 1, lo_col)
                prev_hi = self._get(df, i - 1, hi_col)
                was_inside = (prev_price is not None and prev_lo is not None and prev_hi is not None
                              and prev_lo <= prev_price <= prev_hi)
                return not was_inside

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
                "orb": (_rcol("bull_orb"), _rcol("bear_orb")),
                "initial_balance": (_rcol("ib_above"), _rcol("ib_below")),
                "double_choch_confirmation": (_rcol("bull_double_choch"), _rcol("bear_double_choch")),
                "four_hour_range_reentry": (_rcol("range_long_confirm"), _rcol("range_short_confirm")),
                "asian_range_sweep_reclaim": (_rcol("asian_long_confirm"), _rcol("asian_short_confirm")),
                "doji_confirm": (_rcol("doji_confirm_bull"), _rcol("doji_confirm_bear")),
                "hammer_confirm": (_rcol("hammer_confirm"), _rcol("hammer_confirm")),
                "shooting_star_confirm": (_rcol("shooting_star_confirm"), _rcol("shooting_star_confirm")),
                "morning_star": (_rcol("morning_star_event"), _rcol("morning_star_event")),
                "evening_star": (_rcol("evening_star_event"), _rcol("evening_star_event")),
                "liquidity_sweep_reclaim": (_rcol("level_long_confirm"), _rcol("level_short_confirm")),
                "laxman_break": (_rcol("laxman_long_confirm"), _rcol("laxman_short_confirm")),
                "fvg_reversal": (_rcol("fvg_reversal_long_confirm"), _rcol("fvg_reversal_short_confirm")),
                "order_block_reversal": (_rcol("ob_reversal_long_confirm"), _rcol("ob_reversal_short_confirm")),
                "eqhl_reversal": (_rcol("eqhl_long_confirm"), _rcol("eqhl_short_confirm")),
                "pdhl_reversal": (_rcol("pdhl_long_confirm"), _rcol("pdhl_short_confirm")),
                "mss_reversal": (_rcol("mss_long_confirm"), _rcol("mss_short_confirm")),
                "htf_key_level_engulfing": (_rcol("htf_key_level_long_confirm"), _rcol("htf_key_level_short_confirm")),
                "sniper_headshot_entry": (_rcol("sniper_long_confirm"), _rcol("sniper_short_confirm")),
                "pdhl_mtf_reversal": (_rcol("pdhl_mtf_long_confirm"), _rcol("pdhl_mtf_short_confirm")),
                "cisd_entry": (_rcol("cisd_long_confirm"), _rcol("cisd_short_confirm")),
                "fractal_sweep_reversal": (_rcol("fractal_sweep_long_confirm"), _rcol("fractal_sweep_short_confirm")),
                "liquidity_sweep_multi_confirm": (_rcol("liqsweep_multi_long_confirm"), _rcol("liqsweep_multi_short_confirm")),
                "liquidity_sweep_cisd_swing": (_rcol("liqsweep_cisd_long_confirm"), _rcol("liqsweep_cisd_short_confirm")),
                "ote_liquidity_sweep_reversal": (_rcol("ote_long_confirm"), _rcol("ote_short_confirm")),
                "trendline_breakout": (_rcol("trendline_long_confirm"), _rcol("trendline_short_confirm")),
                "range_breakout_volume_confirm": (_rcol("range_vol_bull_confirm"), _rcol("range_vol_bear_confirm")),
                "htf_ltf_fvg_ob_confluence": (_rcol("confluence_long_confirm"), _rcol("confluence_short_confirm")),
                "heikin_ashi_reversal": (_rcol("ha_long_confirm"), _rcol("ha_short_confirm")),
                "fibonacci_golden_zone": (_rcol("fib_long_confirm"), _rcol("fib_short_confirm")),
                "frvp_poc_reversal": (_rcol("frvp_long_confirm"), _rcol("frvp_short_confirm")),
                "fvg_equilibrium_entry": (_rcol("fvg_eq_long_confirm"), _rcol("fvg_eq_short_confirm")),
                "donchian_lwti_volume_confluence": (_rcol("donchian_long_confirm"), _rcol("donchian_short_confirm")),
                # New Batch 5, Strategy 1: both variants share the same
                # confirm columns (only one is ever in concepts_used per run).
                "liquidity_sweep_engulfing_loose": (_rcol("liqsweep_engulf_long_confirm"), _rcol("liqsweep_engulf_short_confirm")),
                "liquidity_sweep_engulfing_strict": (_rcol("liqsweep_engulf_long_confirm"), _rcol("liqsweep_engulf_short_confirm")),
                # New Batch 5, Strategy 2: two distinct entry modes, each
                # bidirectional (direction picks which side of the same
                # computed columns to read) -- selected via entry_rule_groups.
                "frvp_hvn_reaction": (_rcol("frvp_hvn_support_long"), _rcol("frvp_hvn_resistance_short")),
                "frvp_lvn_breakout": (_rcol("frvp_lvn_breakout_long"), _rcol("frvp_lvn_breakout_short")),
                "sr_liquidity_sweep_sideways": (_rcol("sr_sweep_long_confirm"), _rcol("sr_sweep_short_confirm")),
                "fvg_momentum_pullback": (_rcol("fvgmp_long_confirm"), _rcol("fvgmp_short_confirm")),
                "fvg_pure_inverse": (_rcol("fvgpi_long_confirm"), _rcol("fvgpi_short_confirm")),
                "order_block_trading_loose": (_rcol("obtrade_long_confirm"), _rcol("obtrade_short_confirm")),
                "order_block_trading_strict": (_rcol("obtrade_long_confirm"), _rcol("obtrade_short_confirm")),
                "crt_loose": (_rcol("crt_long_confirm"), _rcol("crt_short_confirm")),
                "crt_strict": (_rcol("crt_long_confirm"), _rcol("crt_short_confirm")),
                "bos_choch_retest": (_rcol("bosc_long_confirm"), _rcol("bosc_short_confirm")),
                "ichimoku_system": (_rcol("ichimoku_long_confirm"), _rcol("ichimoku_short_confirm")),
                "ichimoku_cross": (_rcol("ichimoku_cross_above"), _rcol("ichimoku_cross_below")),
            }
            if cond.name in _DMC_VARIANTS:
                # Computed post-merge in prepare() (not per-role in
                # _compute_concept_columns), always under the literal
                # "entry_" prefix -- DMC's entry/trigger timeframe IS the
                # entry role (4H) per this strategy's own design, so this
                # never needs a non-entry role like laxman_break's short
                # side does. All 3 variants write to the same
                # entry_dmc_long_confirm/entry_dmc_short_confirm columns
                # (only one variant is ever active per strategy run).
                if cond.direction == "bearish":
                    return _within("entry_dmc_short_confirm")
                if cond.direction == "bullish":
                    return _within("entry_dmc_long_confirm")
                return False
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
                # Bare (direction=None): "price is currently inside the
                # value area" -- unchanged, original behavior. A directional
                # value_area (bullish/bearish) means "acceptance" outside
                # the value area on that side (e.g. PBD Volume Profile
                # Strategy's "acceptance above the balance area" / "fade the
                # edge at VAL") -- same real above/below comparison pattern
                # already used for pdh/pdl/support/resistance, just applied
                # to the value-area's own high/low edges (VAH/VAL) instead
                # of a swing level.
                price = self._get(df, i, "close")
                vah = self._get(df, i, _rcol("vah"))
                val = self._get(df, i, _rcol("val"))
                if price is None or vah is None or val is None:
                    return False
                if cond.direction == "bullish":
                    return price > vah
                if cond.direction == "bearish":
                    return price < val
                return val <= price <= vah
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
            if cond.name == "premium_discount_zone":
                in_discount = bool(self._get(df, i, _rcol("in_discount")))
                in_premium = bool(self._get(df, i, _rcol("in_premium")))
                if cond.direction == "bullish":
                    return in_discount
                if cond.direction == "bearish":
                    return in_premium
                return in_discount or in_premium
            if cond.name == "rejection_block":
                return (self._get(df, i, _rcol("bull_rejection_low")) is not None
                        or self._get(df, i, _rcol("bear_rejection_low")) is not None)
            if cond.name == "kill_zone":
                return bool(self._get(df, i, _rcol("in_kill_zone")))
            if cond.name in ("demand_zone", "supply_zone"):
                # A real, fresh-every-bar containment check ("is price
                # CURRENTLY back inside the zone's own low-high range"),
                # unlike order_block/mitigation_block/breaker_block/
                # rejection_block above which only ever check "has a zone
                # ever formed" (permanently True forever once triggered).
                # The zone-forming bar's own close is, by construction,
                # outside [low, high] (concepts.consolidation_impulse_zones
                # only marks a zone on the bar that impulsively broke away
                # from it), so this naturally reads False right at
                # formation and only True once price genuinely returns --
                # no extra "has price left yet" state needed.
                price = self._get(df, i, "close")
                lo_col = _rcol("demand_low" if cond.name == "demand_zone" else "supply_low")
                hi_col = _rcol("demand_high" if cond.name == "demand_zone" else "supply_high")
                lo = self._get(df, i, lo_col)
                hi = self._get(df, i, hi_col)
                if price is None or lo is None or hi is None:
                    return False
                return lo <= price <= hi
            if cond.name == "valid_structure_trend":
                val = self._get(df, i, _rcol("structure_trend"))
                if cond.direction == "bullish":
                    return val == "up"
                if cond.direction == "bearish":
                    return val == "down"
                return val is not None
            if cond.name == "valid_structure_trend_soft":
                # "Not strongly opposing" (Liquidity Sweep Reversal) --
                # bullish here means "not strongly bearish" (trend != down,
                # so "up" OR undetermined both pass), not "must be up".
                if cond.direction == "bullish":
                    return bool(self._get(df, i, _rcol("trend_not_down")))
                if cond.direction == "bearish":
                    return bool(self._get(df, i, _rcol("trend_not_up")))
                return True
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

        if cond.type == "candle_range_pct":
            # (Batch 2, Task 2) "the signal candle's range must be between
            # X% and Y%" -- this bar's own (high-low)/low as a percentage,
            # bounded. role defaults to "entry" like every other condition
            # here; params: {"min_pct":, "max_pct":} (either may be omitted
            # to leave that side unbounded).
            role = cond.role or "entry"
            high = self._get(df, i, f"{role}_high") if role != "entry" else self._get(df, i, "high")
            low = self._get(df, i, f"{role}_low") if role != "entry" else self._get(df, i, "low")
            if high is None or low is None or low <= 0:
                return False
            range_pct = (high - low) / low * 100.0
            min_pct = cond.params.get("min_pct")
            max_pct = cond.params.get("max_pct")
            if min_pct is not None and range_pct < min_pct:
                return False
            if max_pct is not None and range_pct > max_pct:
                return False
            return True

        if cond.type == "candle_body_pct":
            # Two-Focused-Day Push, Part 2 -- "a strong candle" / "not a
            # small or Doji candle" quality filter: this bar's body
            # (|close-open|) as a percentage of its own full high-low
            # range must be at least min_pct. A Doji (open==close) always
            # scores 0% and fails any positive min_pct, matching the
            # plain-language meaning of the filter exactly.
            #
            # max_pct (added for Lower Time Frame Liquidity Reversal's
            # "exhaustion candle": small body, long wick, body no more than
            # 30% of the full range) is the mirror bound -- same shape as
            # candle_range_pct just below, which already supports both
            # min_pct AND max_pct; candle_body_pct only ever had min_pct
            # wired, confirmed missing by that strategy's capability check.
            role = cond.role or "entry"
            prefix = "" if role == "entry" else f"{role}_"
            o = self._get(df, i, f"{prefix}open")
            h = self._get(df, i, f"{prefix}high")
            l = self._get(df, i, f"{prefix}low")
            c = self._get(df, i, f"{prefix}close")
            if o is None or h is None or l is None or c is None or h <= l:
                return False
            body_pct = abs(c - o) / (h - l) * 100.0
            min_pct = cond.params.get("min_pct")
            max_pct = cond.params.get("max_pct")
            if min_pct is not None and body_pct < min_pct:
                return False
            if max_pct is not None and body_pct > max_pct:
                return False
            return True

        return False

    def _compute_stop_loss(self, df, i, price, direction):
        spec = self.config.stop_loss
        if spec.type == "fixed_pct" and spec.value is not None:
            pct = spec.value / 100.0
            return price * (1 - pct) if direction == "bullish" else price * (1 + pct)
        if spec.type == "atr_multiple" and spec.value is not None:
            atr_val = self._get(df, i, f"entry_atr_{spec.atr_period or 14}")
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
            # entry_demand_low/entry_supply_high (Supply/Demand Zone
            # strategy) checked FIRST -- a demand/supply zone is a more
            # specific, deliberately-marked structural anchor than a plain
            # order block, so a strategy that actually declared demand_zone/
            # supply_zone in concepts_used should have its own zone win over
            # the generic fallbacks (which stay unaffected for every other
            # strategy: these columns simply don't exist unless demand_zone/
            # supply_zone is in concepts_used, so _get() returns None and
            # this candidate is skipped exactly like today).
            # Candlestick Pattern Reversal Strategy's pattern-specific
            # extremes (Doji/Hammer/Morning Star low, Doji/Shooting Star/
            # Evening Star high) checked FIRST, same reasoning as demand_
            # zone/supply_zone above -- these columns simply don't exist
            # for any other strategy, so _get() returns None and the
            # candidate is skipped exactly like today.
            #
            # spec.value (optional, %): "structure" never read this field
            # before -- every existing strategy that uses it leaves value
            # unset (None), so buffer_pct is 0.0 and behavior is BYTE-FOR-
            # BYTE unchanged for them. A strategy that DOES set it (e.g.
            # Candlestick Pattern Reversal, verified via
            # cost_model.check_buffer_safety() before finalizing) gets a
            # real safety margin instead of the raw zone value.
            buffer_pct = (spec.value or 0.0) / 100.0
            if direction == "bullish":
                # entry_laxman_trigger_low: Laxman Rekha's long-side SL (the
                # active trigger candle's own low, its long entries run on
                # the "entry" role natively). daily_tf_next_prior_swing_low:
                # Dumb Money Concepts' SL ("behind the next level behind"),
                # computed on the daily_tf role and merged onto entry.
                # entry_range_vol_sl_bull (New Batch 3, Strategy 2): the
                # breakout/breakdown candle's OWN low, when this signal came
                # from range_breakout_volume_confirm -- "the extreme of the
                # breakout/breakdown candle" -- sparse (only non-NaN at the
                # exact confirm bar), so it never affects any other
                # strategy. entry_confluence_sl_bull (Strategy 3): the FVG
                # zone's 50% level, ONLY populated when that gap's own
                # producing candle was unusually large -- when NOT large,
                # this column is NaN and the search falls through to
                # entry_fvg_bull_low below unchanged, i.e. "slightly beyond
                # the FVG zone" for the normal case with no new code.
                for col in ("entry_ichimoku_sl_bull", "entry_bosc_sl_bull", "entry_crt_sl_bull", "entry_obtrade_sl_bull", "entry_fvgpi_sl_bull", "entry_fvgmp_sl_bull", "entry_sr_sweep_sl_bull", "entry_frvp2_sl_bull", "entry_liqsweep_engulf_sl_bull", "entry_range_vol_sl_bull", "entry_confluence_sl_bull",
                            "entry_ha_sl_bull", "entry_fib_sl_bull", "entry_frvp_sl_bull", "entry_fvg_eq_sl_bull",
                            "entry_laxman_trigger_low", "daily_tf_next_prior_swing_low",
                            "entry_doji_pending_low", "entry_hammer_pending_low", "entry_morning_star_low",
                            "entry_demand_low", "entry_bull_ob_low", "entry_fvg_bull_low",
                            "entry_eq_low_level", "entry_pdl", "entry_support", "h4_support", "bias_support",
                            "bias_donchian_mid"):
                    zone = self._get(df, i, col)
                    if zone is not None and zone < price:
                        return zone * (1 - buffer_pct)
            else:
                # short_tf_laxman_trigger_high: Laxman Rekha's short-side SL
                # -- shorts run on the "short_tf" (15m) role, a genuinely
                # different entry timeframe than the long side's "entry"
                # (5m), see StrategyConfig.timeframes_by_role.
                for col in ("entry_ichimoku_sl_bear", "entry_bosc_sl_bear", "entry_crt_sl_bear", "entry_obtrade_sl_bear", "entry_fvgpi_sl_bear", "entry_fvgmp_sl_bear", "entry_sr_sweep_sl_bear", "entry_frvp2_sl_bear", "entry_liqsweep_engulf_sl_bear", "entry_range_vol_sl_bear", "entry_confluence_sl_bear",
                            "entry_ha_sl_bear", "entry_fib_sl_bear", "entry_frvp_sl_bear", "entry_fvg_eq_sl_bear",
                            "short_tf_laxman_trigger_high", "daily_tf_next_prior_swing_high",
                            "entry_doji_pending_high", "entry_shooting_star_pending_high", "entry_evening_star_high",
                            "entry_supply_high", "entry_bear_ob_high", "entry_fvg_bear_high",
                            "entry_eq_high_level", "entry_pdh", "entry_resistance", "h4_resistance", "bias_resistance",
                            "bias_donchian_mid"):
                    zone = self._get(df, i, col)
                    if zone is not None and zone > price:
                        return zone * (1 + buffer_pct)
            return None
        if spec.type == "signal_candle":
            # (Batch 2, Task 2) "stop-loss = the signal candle's own high
            # (short) / low (long), buffered by `value` percent" -- e.g.
            # "signal candle's high * 1.003". Bar `i` here IS the signal
            # candle: on_bar() only ever calls this at the exact bar a
            # fresh entry condition became true, so no separate lookup or
            # extra plumbing is needed to find "the signal candle" -- it's
            # simply this bar.
            buffer_pct = (spec.value or 0.0) / 100.0
            if direction == "bullish":
                low = self._array(df, "low")
                if low is None:
                    return None
                return float(low[i]) * (1 - buffer_pct)
            else:
                high = self._array(df, "high")
                if high is None:
                    return None
                return float(high[i]) * (1 + buffer_pct)
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
            atr_val = self._get(df, i, f"entry_atr_{spec.atr_period or 14}")
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
                # daily_tf_move_origin_for_support: Dumb Money Concepts'
                # primary TP target ("the origin of the move that brought
                # price to this level"), checked first -- falls through to
                # the plain entry_resistance already in this list (DMC's
                # own stated alternative target: "next major structure
                # level") if the origin snapshot isn't available yet.
                for col in ("entry_bosc_tp_bull", "entry_obtrade_tp_bull", "entry_sr_sweep_fixed_tp_bull", "entry_frvp2_tp_bull", "daily_tf_move_origin_for_support", "entry_bear_ob_high", "entry_fvg_bear_high",
                            "bias_resistance", "entry_resistance", "entry_pdh"):
                    zone = self._get(df, i, col)
                    if zone is not None and zone > price:
                        return zone
            else:
                for col in ("entry_bosc_tp_bear", "entry_obtrade_tp_bear", "entry_sr_sweep_fixed_tp_bear", "entry_frvp2_tp_bear", "daily_tf_move_origin_for_resistance", "entry_bull_ob_low", "entry_fvg_bull_low",
                            "bias_support", "entry_support", "entry_pdl"):
                    zone = self._get(df, i, col)
                    if zone is not None and zone < price:
                        return zone
            return None
        if spec.type == "structure_or_rr":
            # Sniper Headshot Entry: "next logical structural level ...
            # placed slightly inside the structural extreme (buffer); if no
            # clear structure target exists, fall back to fixed RR" --
            # same structural candidate search as "structure" above
            # (unaffected by this addition, still its own separate branch),
            # with a small own-default inward buffer (0.1%, source gives no
            # exact number) so the target sits just short of the exact
            # swing extreme, plus a real RR fallback (spec.value) for when
            # no structural level is available yet -- "structure" alone has
            # no such fallback, which is exactly the gap this strategy's
            # own rules call out explicitly.
            inward_buffer = 0.001
            zone_target = None
            if direction == "bullish":
                for col in ("daily_tf_move_origin_for_support", "entry_bear_ob_high", "entry_fvg_bear_high",
                            "bias_resistance", "entry_resistance", "entry_pdh"):
                    zone = self._get(df, i, col)
                    if zone is not None and zone > price:
                        zone_target = zone * (1 - inward_buffer)
                        break
            else:
                for col in ("daily_tf_move_origin_for_resistance", "entry_bull_ob_low", "entry_fvg_bull_low",
                            "bias_support", "entry_support", "entry_pdl"):
                    zone = self._get(df, i, col)
                    if zone is not None and zone < price:
                        zone_target = zone * (1 + inward_buffer)
                        break
            if zone_target is not None:
                return zone_target
            if spec.value is not None and sl is not None:
                risk_distance = abs(price - sl)
                return price + risk_distance * spec.value if direction == "bullish" else price - risk_distance * spec.value
            return None
        return None

    def _compute_primary_target(self, df, i, direction, lookback_bars):
        """(Batch 2, Task 2) "the lowest low (short) / highest high (long)
        of the preceding N candles before entry" -- purely a reference
        price for min_risk_reward_filter's discard check, independent of
        whatever take_profit is actually configured to be. Causal: only
        ever reads bars strictly BEFORE i (the signal bar itself is
        excluded), same convention as every other structural lookup in
        this file."""
        start = max(0, i - lookback_bars)
        if start >= i:
            return None
        if direction == "bullish":
            highs = self._array(df, "high")
            if highs is None:
                return None
            return float(highs[start:i].max())
        else:
            lows = self._array(df, "low")
            if lows is None:
                return None
            return float(lows[start:i].min())

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
