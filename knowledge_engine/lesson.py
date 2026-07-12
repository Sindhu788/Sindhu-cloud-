"""A Lesson is CEO-authored guidance that gates trades during backtesting
(and, later, paper trading / evolution). No AI, no auto-generation: the
description is converted into structured conditions with the exact same
deterministic keyword parser strategies use (backtest_engine.strategy_parser),
so a lesson like "avoid buying when RSI above 70" becomes a real,
evaluable rule -- never a guess.
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from backtest_engine.strategy_parser import parse_conditions

CATEGORIES = [
    "Market Structure", "Trend", "Liquidity", "BOS", "CHoCH", "Order Blocks",
    "Fair Value Gap", "Support", "Resistance", "Risk Management", "Psychology",
    "Entry Rules", "Exit Rules", "Money Management", "Sessions", "News",
    "Indicators", "Other",
]

# Wording convention (still pure keyword matching, no AI) that decides
# whether a lesson's condition is a veto ("avoid X") or a requirement
# ("only trade when X"). Defaults to veto, since most guardrail-style
# lessons are phrased as things to avoid.
_REQUIRE_KEYWORDS = ["only", "require", "must", "should", "chahiye", "zaroor", "zaroori"]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _detect_rule_type(text):
    lower = (text or "").lower()
    return "require_if_true" if any(k in lower for k in _REQUIRE_KEYWORDS) else "block_if_true"


def _detect_direction(text):
    lower = (text or "").lower()
    if any(w in lower for w in ("buy", "long", "bullish", "kharid")):
        return "bullish"
    if any(w in lower for w in ("sell", "short", "bearish", "farokht", "bech")):
        return "bearish"
    return None


@dataclass
class Lesson:
    id: str = ""
    title: str = ""
    category: str = "Other"
    description: str = ""
    priority: str = "Medium"          # Low / Medium / High / Critical
    status: str = "active"             # active / disabled / draft
    notes: str = ""
    apply_backtesting: bool = True
    apply_paper_trading: bool = True
    apply_evolution: bool = True
    rule_type: str = "block_if_true"
    direction: Optional[str] = None
    conditions: list = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    version: int = 1
    tags: list = field(default_factory=list)
    supported_market_types: list = field(default_factory=list)   # empty = all
    supported_timeframes: list = field(default_factory=list)     # empty = all

    def to_storage_dict(self):
        d = asdict(self)
        d["conditions"] = [asdict(c) if not isinstance(c, dict) else c for c in self.conditions]
        return d

    def is_enforceable(self):
        return len(self.conditions) > 0

    def matches_market_type(self, market_type):
        return not self.supported_market_types or market_type in self.supported_market_types

    def matches_timeframe(self, timeframe):
        return not self.supported_timeframes or timeframe in self.supported_timeframes


def new_lesson(title, category, description="", priority="Medium", notes="",
               apply_backtesting=True, apply_paper_trading=True, apply_evolution=True,
               status="active", tags=None, supported_market_types=None, supported_timeframes=None,
               version=1):
    if category not in CATEGORIES:
        category = "Other"

    raw_conditions = parse_conditions(description) if description else []
    enforceable = [c for c in raw_conditions if c.type != "raw"]

    now = now_iso()
    return Lesson(
        id=uuid.uuid4().hex[:12],
        title=title, category=category, description=description,
        priority=priority, status=status, notes=notes,
        apply_backtesting=apply_backtesting, apply_paper_trading=apply_paper_trading,
        apply_evolution=apply_evolution,
        rule_type=_detect_rule_type(description),
        direction=_detect_direction(description),
        conditions=enforceable,
        created_at=now, updated_at=now, version=version,
        tags=tags or [], supported_market_types=supported_market_types or [],
        supported_timeframes=supported_timeframes or [],
    )


def from_storage_dict(d):
    from backtest_engine.strategy_config import Condition
    d = dict(d)
    d["conditions"] = [Condition(**c) for c in d.get("conditions", [])]
    return Lesson(**d)
