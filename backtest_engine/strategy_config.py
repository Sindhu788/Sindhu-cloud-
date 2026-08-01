"""The structured, executable form a parsed strategy is converted into.
ConfiguredStrategy (strategy_config -> Strategy) reads this directly; the
parser's whole job is filling this in from free text without guessing."""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Condition:
    """One atomic testable condition. `type` selects which fields matter:
    - "indicator_compare":     indicator, params, op, value        (e.g. RSI < 30)
    - "price_compare":         op, indicator, params                (e.g. close > EMA50)
    - "indicator_vs_indicator": indicator, params, op, indicator2, params2
                                (e.g. EMA20 > EMA50 -- an indicator compared
                                against ANOTHER indicator instead of a fixed
                                number; both read from the same `role`)
    - "concept":                name, direction (optional)          (e.g. bullish BOS)
    - "session":                 name                                 (e.g. london)
    - "trend":                   direction                             (e.g. up)
    - "candle_range_pct":       params={"min_pct":, "max_pct":}     (this bar's (high-low)/low
                                as a percentage must fall within [min_pct, max_pct] -- e.g. "the
                                signal candle's range must be between 0.15% and 3.0%")
    - "raw":                     text                                  (unparsed -- needs clarification)
    """
    type: str
    indicator: Optional[str] = None
    params: dict = field(default_factory=dict)
    op: Optional[str] = None
    value: Optional[float] = None
    name: Optional[str] = None
    direction: Optional[str] = None
    text: Optional[str] = None
    role: Optional[str] = None  # which timeframe role this condition is evaluated on
    lookback_bars: Optional[int] = None
    # Only meaningful for type="concept": how many recent bars (including the
    # current one) to check for this concept having been True, instead of
    # requiring it on this exact bar. None = use the evaluator's default
    # (currently 10); 1 = strict same-bar (the original, pre-Phase-6
    # behavior). Ignored entirely for every other condition type.
    indicator2: Optional[str] = None   # only for type="indicator_vs_indicator"
    params2: dict = field(default_factory=dict)  # only for type="indicator_vs_indicator"

    def is_unclear(self):
        return self.type == "raw"


@dataclass
class SLTPSpec:
    """How stop-loss / take-profit is derived.
    type: "fixed_pct" (value = %), "atr_multiple" (value = multiple),
          "structure" (below/above last swing, order block, or FVG), "rr" (TP
          only, value = risk:reward multiple), "level" (TP only, targets a
          named price level -- see `level`), "signal_candle" (SL only, value
          = buffer %: the signal bar's own high (short) or low (long),
          buffered by `value` percent -- e.g. "stop-loss = signal candle's
          high * 1.003"), or "unknown" (couldn't detect)."""
    type: str = "unknown"
    value: Optional[float] = None
    level: Optional[str] = None  # "pdh" | "pdl" -- only used when type == "level"


@dataclass
class StrategyConfig:
    name: str
    raw_text: str = ""

    timeframes: dict = field(default_factory=dict)          # {role: "1h", ...}
    indicators: list = field(default_factory=list)           # [{"name":"ema","params":{"period":50},"role":"trend"}]
    concepts_used: list = field(default_factory=list)         # ["bos", "fvg", ...]

    entry_conditions: list = field(default_factory=list)      # list[Condition] -- legacy single-direction entry gate
    exit_conditions: list = field(default_factory=list)
    confirmation_conditions: list = field(default_factory=list)
    # Two mutually-exclusive rule sets for a strategy that describes separate
    # Long and Short entry rules (each independently AND-ed, exactly like
    # entry_conditions is today) instead of one shared gate. When either of
    # these is non-empty, ConfiguredStrategy.on_bar() uses THEM instead of
    # entry_conditions -- a strategy that only ever populates entry_conditions
    # (every strategy saved before this feature) is completely unaffected.
    long_entry_conditions: list = field(default_factory=list)   # list[Condition]
    short_entry_conditions: list = field(default_factory=list)  # list[Condition]
    # Branching/conditional entry logic: N independent alternative entry
    # paths (e.g. "if the market shows a P-shape profile, enter this way;
    # if B-shape, enter that way; if D-shape, enter a third way"), each its
    # own AND-gated rule set, evaluated as OR across groups -- ANY group
    # whose conditions are all true fires an entry in that group's
    # direction. This is what entry_conditions/long_entry_conditions/
    # short_entry_conditions structurally cannot express (each of those is
    # exactly ONE AND-gate per direction, never a menu of alternatives).
    # [{"label": "P-Shape Continuation", "direction": "bullish"|"bearish",
    #   "conditions": [Condition, ...]}, ...]. When non-empty, this takes
    # priority over entry_conditions/long_entry_conditions/
    # short_entry_conditions (which should be left empty) -- see
    # ConfiguredStrategy.on_bar().
    entry_rule_groups: list = field(default_factory=list)

    stop_loss: SLTPSpec = field(default_factory=SLTPSpec)
    take_profit: SLTPSpec = field(default_factory=SLTPSpec)
    risk_pct: Optional[float] = None
    risk_reward: Optional[float] = None

    # -------------------------------------------- Pre-trade discard filters
    # (Batch 2, Task 2) A signal that would otherwise fire is instead
    # discarded (no trade at all -- distinct from stop_loss/take_profit,
    # which shape a trade that DOES happen) when these don't hold. Both
    # None = no filtering, byte-for-byte unchanged behavior for every
    # strategy saved before this feature existed.
    #
    # {"min_pct":, "max_pct":} -- the computed stop-loss distance, as a
    # percent of entry price, must fall within this range or the trade is
    # skipped (e.g. "if SL distance is <0.15% or >1.5% of entry, don't
    # take the trade").
    sl_distance_filter_pct: Optional[dict] = None
    # A minimum required risk:reward, checked against a PRIMARY reference
    # target -- the highest/lowest price of the `primary_target_lookback_bars`
    # candles immediately before entry (e.g. "the lowest low of the
    # preceding 200 candles") -- independent of whatever take_profit itself
    # is configured to be (e.g. take_profit can target a farther level for
    # a runner position while this filter still judges the trade against
    # the nearer, primary target). Only applied when
    # primary_target_lookback_bars is also set.
    min_risk_reward_filter: Optional[float] = None
    primary_target_lookback_bars: Optional[int] = None

    session_filter: list = field(default_factory=list)        # ["london", "ny"]
    trend_filter: Optional[str] = None                          # "up" / "down" / None
    day_filter: list = field(default_factory=list)             # ["monday", "friday"]
    breakeven_at_rr: Optional[float] = None                      # move stop to entry once unrealized profit reaches this many R

    # -------------------------------------------- Trade Execution Engine
    # How a signal actually becomes a filled position. "market" and
    # "current_candle_close" are two names for the SAME fill (the close of
    # the bar the signal fired on) -- a bar-based backtest with no
    # intra-bar order book has no way to distinguish them, so both are
    # accepted and documented as identical rather than one silently being
    # ignored. Default "market" reproduces every strategy's behavior from
    # before this field existed, byte-for-byte.
    entry_type: str = "market"
    # "limit"/"stop" trigger price = signal-bar close offset by this percent
    # (limit: against the trade direction, i.e. a pullback; stop: with the
    # trade direction, i.e. a breakout). None/0 means the trigger equals the
    # signal price exactly -- mechanically valid (it still goes through the
    # real pending-order fill check) but only meaningfully different from
    # "market" once a real offset is set.
    entry_price_offset_pct: Optional[float] = None
    # {"trigger_rr": 1.0, "close_fraction": 0.5} -- close close_fraction of
    # the position once unrealized profit reaches trigger_rr multiples of
    # the original risk (same "R" as breakeven_at_rr), leaving the rest
    # running under its own original stop/target. None = disabled.
    partial_take_profit: Optional[dict] = None
    # {"type": "pct"|"atr_multiple", "value": N} -- stop trails the best
    # price seen since entry, only ever tightening, never loosening.
    # "pct": trail N% behind the best price. "atr_multiple": trail N*ATR(14)
    # behind it (falls back to not trailing on a bar with no ATR column
    # computed, rather than guessing a value). None = disabled.
    trailing_stop: Optional[dict] = None
    # Force-close the position after this many bars have elapsed since
    # entry, at that bar's close. None = disabled (position only ever
    # closes via stop-loss/take-profit/exit signal/end-of-data, as before).
    time_exit_bars: Optional[int] = None

    tags: list = field(default_factory=list)
    favourite: bool = False

    missing: list = field(default_factory=list)                # required fields not detected
    warnings: list = field(default_factory=list)                # detected but ambiguous

    def to_dict(self):
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d):
        d = dict(d)
        d["stop_loss"] = SLTPSpec(**d.get("stop_loss", {}))
        d["take_profit"] = SLTPSpec(**d.get("take_profit", {}))
        d["entry_conditions"] = [Condition(**c) for c in d.get("entry_conditions", [])]
        d["exit_conditions"] = [Condition(**c) for c in d.get("exit_conditions", [])]
        d["confirmation_conditions"] = [Condition(**c) for c in d.get("confirmation_conditions", [])]
        d["long_entry_conditions"] = [Condition(**c) for c in d.get("long_entry_conditions", [])]
        d["short_entry_conditions"] = [Condition(**c) for c in d.get("short_entry_conditions", [])]
        d["entry_rule_groups"] = [
            {**g, "conditions": [Condition(**c) for c in g.get("conditions", [])]}
            for g in d.get("entry_rule_groups", [])
        ]
        return StrategyConfig(**d)
