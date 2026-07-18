"""The structured, executable form a parsed strategy is converted into.
ConfiguredStrategy (strategy_config -> Strategy) reads this directly; the
parser's whole job is filling this in from free text without guessing."""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Condition:
    """One atomic testable condition. `type` selects which fields matter:
    - "indicator_compare": indicator, params, op, value        (e.g. RSI < 30)
    - "price_compare":     op, indicator, params                (e.g. close > EMA50)
    - "concept":           name, direction (optional)            (e.g. bullish BOS)
    - "session":           name                                  (e.g. london)
    - "trend":             direction                             (e.g. up)
    - "raw":               text                                  (unparsed -- needs clarification)
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

    def is_unclear(self):
        return self.type == "raw"


@dataclass
class SLTPSpec:
    """How stop-loss / take-profit is derived.
    type: "fixed_pct" (value = %), "atr_multiple" (value = multiple),
          "structure" (below/above last swing, order block, or FVG), "rr" (TP
          only, value = risk:reward multiple), "level" (TP only, targets a
          named price level -- see `level`), or "unknown" (couldn't detect)."""
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

    entry_conditions: list = field(default_factory=list)      # list[Condition]
    exit_conditions: list = field(default_factory=list)
    confirmation_conditions: list = field(default_factory=list)

    stop_loss: SLTPSpec = field(default_factory=SLTPSpec)
    take_profit: SLTPSpec = field(default_factory=SLTPSpec)
    risk_pct: Optional[float] = None
    risk_reward: Optional[float] = None

    session_filter: list = field(default_factory=list)        # ["london", "ny"]
    trend_filter: Optional[str] = None                          # "up" / "down" / None
    day_filter: list = field(default_factory=list)             # ["monday", "friday"]
    breakeven_at_rr: Optional[float] = None                      # move stop to entry once unrealized profit reaches this many R

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
        return StrategyConfig(**d)
