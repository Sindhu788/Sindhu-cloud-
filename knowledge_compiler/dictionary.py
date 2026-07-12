"""Canonical trading-terminology dictionary shared by the whole Knowledge
Compiler pipeline. Extends -- never modifies -- backtest_engine.strategy_parser's
own concept/session tables: every alias that already maps to something the
execution engine understands keeps that same canonical key, so normalize_text()
can rewrite an unfamiliar phrasing (e.g. "PDH", "demand zone", "OB") into
wording strategy_parser already parses, without duplicating its regex logic.

Terms with concept_key=None are recognized and tagged (useful for
classification, tagging, and lesson categorization) but have no executable
primitive in concepts.py yet -- referencing one in a strategy still produces
an honest "raw"/unclear condition rather than a silent guess, exactly like
any other term strategy_parser doesn't recognize.
"""

import re
from dataclasses import dataclass, field

from backtest_engine.strategy_parser import CONCEPT_KEYWORDS, SESSION_NAMES

CATEGORY_STRUCTURE = "structure"
CATEGORY_INDICATOR = "indicator"
CATEGORY_SESSION = "session"
CATEGORY_TREND = "trend"
CATEGORY_RISK = "risk"
CATEGORY_PSYCHOLOGY = "psychology"

# Maps a dictionary canonical term to one of knowledge_engine.lesson.CATEGORIES
# so the Lesson Extractor can auto-categorize without guessing.
LESSON_CATEGORY_MAP = {
    "bos": "BOS", "choch": "CHoCH", "order_block": "Order Blocks",
    "breaker_block": "Market Structure", "fvg": "Fair Value Gap",
    "liquidity_sweep": "Liquidity", "support": "Support", "resistance": "Resistance",
    "trend_filter": "Trend", "session_filter": "Sessions",
    "asian": "Sessions", "london": "Sessions", "ny": "Sessions",
    "ema": "Indicators", "sma": "Indicators", "vwap": "Indicators",
    "rsi": "Indicators", "macd": "Indicators", "atr": "Indicators", "volume": "Indicators",
    "pdh": "Market Structure", "pdl": "Market Structure", "pdc": "Market Structure",
    "pwh": "Market Structure", "pwl": "Market Structure", "poi": "Market Structure",
    "mitigation": "Market Structure", "inducement": "Market Structure",
    "equal_highs_lows": "Market Structure", "premium_discount": "Market Structure",
    "stop_loss": "Risk Management", "take_profit": "Risk Management",
    "risk_reward": "Risk Management", "risk_per_trade": "Risk Management",
    "position_sizing": "Money Management", "drawdown": "Money Management",
    "fomo": "Psychology", "revenge_trading": "Psychology", "overtrading": "Psychology",
    "discipline": "Psychology", "patience": "Psychology", "emotional_trading": "Psychology",
}


@dataclass
class DictEntry:
    canonical: str
    category: str
    aliases: list = field(default_factory=list)
    concept_key: str = None   # key into backtest_engine's executable concept table, or None
    description: str = ""


_ENTRIES = {}


def _entry(canonical, category, aliases, concept_key=None, description=""):
    _ENTRIES[canonical] = DictEntry(canonical, category, list(aliases), concept_key, description)


# --- reuse existing, already-executable concept/session keywords verbatim ---
_INDICATOR_KEYS = {"ema", "sma", "vwap", "rsi", "macd", "atr", "volume"}
for _key, _aliases in CONCEPT_KEYWORDS.items():
    if _key in _INDICATOR_KEYS:
        _cat = CATEGORY_INDICATOR
    elif _key == "session_filter":
        _cat = CATEGORY_SESSION
    elif _key == "trend_filter":
        _cat = CATEGORY_TREND
    else:
        _cat = CATEGORY_STRUCTURE
    _entry(_key, _cat, _aliases, concept_key=_key)

for _key, _aliases in SESSION_NAMES.items():
    _entry(_key, CATEGORY_SESSION, _aliases, concept_key=_key)

# --- structure/concept terms with no execution primitive yet (recognized & tagged only) ---
_entry("pdh", CATEGORY_STRUCTURE, ["pdh", "previous day high", "prior day high", "yesterday's high", "yesterday high"], description="Previous Day High")
_entry("pdl", CATEGORY_STRUCTURE, ["pdl", "previous day low", "prior day low", "yesterday's low", "yesterday low"], description="Previous Day Low")
_entry("pdc", CATEGORY_STRUCTURE, ["pdc", "previous day close", "prior day close"], description="Previous Day Close")
_entry("pwh", CATEGORY_STRUCTURE, ["pwh", "previous week high", "prior week high"], description="Previous Week High")
_entry("pwl", CATEGORY_STRUCTURE, ["pwl", "previous week low", "prior week low"], description="Previous Week Low")
_entry("poi", CATEGORY_STRUCTURE, ["poi", "point of interest"], description="Point Of Interest")
_entry("mitigation", CATEGORY_STRUCTURE, ["mitigation", "mitigated", "mitigation block"], description="Mitigation Block")
_entry("inducement", CATEGORY_STRUCTURE, ["inducement", "induce"], description="Inducement")
_entry("equal_highs_lows", CATEGORY_STRUCTURE, ["equal highs", "equal lows", "eqh", "eql"], description="Equal Highs/Lows")
_entry("premium_discount", CATEGORY_STRUCTURE, ["premium", "discount", "ote", "optimal trade entry"], description="Premium/Discount (OTE)")

# --- extra aliases for EXISTING executable concepts, phrased more ways than
# strategy_parser's own list -- normalize_text() rewrites these to a phrase
# strategy_parser already recognizes so parse_conditions still works. ---
_entry("order_block_extra", CATEGORY_STRUCTURE, ["bullish ob", "bearish ob", "demand block", "supply block"], concept_key="order_block")
_entry("fvg_extra", CATEGORY_STRUCTURE, ["unfilled fvg", "imbalance zone", "price imbalance"], concept_key="fvg")
_entry("bos_extra", CATEGORY_STRUCTURE, ["structure break", "break in structure", "market structure break"], concept_key="bos")
_entry("liquidity_extra", CATEGORY_STRUCTURE, ["sweep the liquidity", "grab liquidity", "hunted stops", "liquidity pool"], concept_key="liquidity_sweep")
_entry("support_extra", CATEGORY_STRUCTURE, ["support zone", "support level", "demand zone", "demand area"], concept_key="support")
_entry("resistance_extra", CATEGORY_STRUCTURE, ["resistance zone", "resistance level", "supply zone", "supply area"], concept_key="resistance")
_entry("trend_extra", CATEGORY_TREND, ["trending market", "trend direction", "market trend", "with the trend"], concept_key="trend_filter")
_entry("london_killzone", CATEGORY_SESSION, ["london killzone", "london kill zone"], concept_key="london")
_entry("ny_killzone", CATEGORY_SESSION, ["ny killzone", "new york killzone", "ny kill zone"], concept_key="ny")
_entry("asian_killzone", CATEGORY_SESSION, ["asian killzone", "asia killzone"], concept_key="asian")

# --- risk terms (classification + lesson tagging only; Risk Manager already
# implements sizing/slippage/limits elsewhere -- this is not a second engine) ---
_entry("stop_loss", CATEGORY_RISK, ["stop loss", "stoploss", " sl "])
_entry("take_profit", CATEGORY_RISK, ["take profit", " tp "])
_entry("risk_reward", CATEGORY_RISK, ["risk reward", "risk:reward", "risk to reward", " rr "])
_entry("risk_per_trade", CATEGORY_RISK, ["risk per trade", "% risk", "risk percentage", "risk percent"])
_entry("position_sizing", CATEGORY_RISK, ["position size", "position sizing", "lot size"])
_entry("drawdown", CATEGORY_RISK, ["drawdown", "max drawdown", "maximum drawdown"])

# --- psychology terms (classification + lesson tagging only) ---
_entry("fomo", CATEGORY_PSYCHOLOGY, ["fomo", "fear of missing out"])
_entry("revenge_trading", CATEGORY_PSYCHOLOGY, ["revenge trade", "revenge trading"])
_entry("overtrading", CATEGORY_PSYCHOLOGY, ["overtrading", "over-trading", "too many trades"])
_entry("discipline", CATEGORY_PSYCHOLOGY, ["discipline", "disciplined", "follow your plan"])
_entry("patience", CATEGORY_PSYCHOLOGY, ["patience", "patient", "wait for the setup", "wait for setup"])
_entry("emotional_trading", CATEGORY_PSYCHOLOGY, ["emotional trading", "emotion", "fear and greed", "greed and fear"])

# Build a flat alias -> canonical lookup, longest alias first so multi-word
# phrases match before a shorter substring of them would.
_ALIAS_MAP = {}
for _e in _ENTRIES.values():
    for _a in _e.aliases:
        _ALIAS_MAP[_a.strip().lower()] = _e.canonical
_ALIASES_BY_LENGTH = sorted(_ALIAS_MAP.keys(), key=len, reverse=True)
_ALIAS_PATTERNS = {a: re.compile(r"(?<![a-z0-9])" + re.escape(a.strip()) + r"(?![a-z0-9])", re.IGNORECASE) for a in _ALIASES_BY_LENGTH}


def all_entries():
    return list(_ENTRIES.values())


def entries_by_category(category):
    return [e for e in _ENTRIES.values() if e.category == category]


_ALIAS_CONTAINS_CACHE = {}


def alias_in_text(alias, text_lower):
    """Word-boundary-aware check for whether `alias` appears in `text_lower`
    (already lowercased). Plain substring containment lets short aliases
    like "sma" or "ob" false-positive-match inside ordinary words ("sma" is
    literally the first three letters of "Smart") -- this is what every
    dictionary alias scan (classifier scoring, lesson tagging, concept
    tracking) should use instead of the `in` operator."""
    key = alias.strip().lower()
    pattern = _ALIAS_CONTAINS_CACHE.get(key)
    if pattern is None:
        pattern = re.compile(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", re.IGNORECASE)
        _ALIAS_CONTAINS_CACHE[key] = pattern
    return bool(pattern.search(text_lower))


def lookup(term):
    """Resolve a raw alias/term to its DictEntry, or None if unrecognized."""
    if not term:
        return None
    canonical = _ALIAS_MAP.get(term.strip().lower())
    return _ENTRIES.get(canonical) if canonical else _ENTRIES.get(term.strip().lower())


def normalize_term(raw):
    """Return the canonical name for a raw alias, or the lowercased input
    unchanged if it isn't a recognized term."""
    entry = lookup(raw)
    return entry.canonical if entry else (raw or "").strip().lower()


def lesson_category_for(canonical_or_alias):
    """Best-guess Lesson category (one of knowledge_engine.lesson.CATEGORIES)
    for a recognized dictionary term, or None if there's no clean mapping --
    callers fall back to "Other" rather than guessing further."""
    entry = lookup(canonical_or_alias)
    key = entry.canonical if entry else canonical_or_alias
    return LESSON_CATEGORY_MAP.get(key)


# Categories safe to rewrite in text that will be handed to strategy_parser.
# CATEGORY_RISK / CATEGORY_PSYCHOLOGY are deliberately excluded: strategy_parser's
# own SL/TP/RR/risk regexes key off literal words like "sl", "tp", "rr",
# "risk" -- rewriting those to a canonical tag (e.g. "sl" -> "stop_loss")
# would silently break detection that already works. Risk/psychology terms
# are looked up against the ORIGINAL text instead (classifier, lesson tagging).
_NORMALIZABLE_CATEGORIES = {CATEGORY_STRUCTURE, CATEGORY_INDICATOR, CATEGORY_SESSION, CATEGORY_TREND}
_NORMALIZE_ALIASES = [a for a in _ALIASES_BY_LENGTH if _ENTRIES[_ALIAS_MAP[a]].category in _NORMALIZABLE_CATEGORIES]


def normalize_text(text):
    """Rewrite every recognized structural/indicator/session/trend alias in
    `text` to a canonical phrase that the existing strategy_parser already
    understands (for concept_key entries) or to its own canonical name (for
    tag-only structural entries like PDH/PDL). Longest aliases are replaced
    first so multi-word phrases win over substrings. Risk and psychology
    terms are intentionally never rewritten here (see _NORMALIZABLE_CATEGORIES).
    Unrecognized wording is left as-is and surfaced later as an unresolved/raw
    fragment, never guessed at.
    """
    if not text:
        return text
    result = text
    for alias in _NORMALIZE_ALIASES:
        canonical = _ALIAS_MAP[alias]
        entry = _ENTRIES[canonical]
        replacement = entry.canonical if entry.concept_key is None else entry.concept_key
        if alias == replacement.lower():
            continue
        result = _ALIAS_PATTERNS[alias].sub(replacement, result)
    return result
