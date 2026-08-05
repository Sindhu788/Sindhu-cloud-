"""Keyword/pattern based strategy parser -- no AI/LLM calls. Understands
English, Roman Urdu, and mixed text because the trading jargon itself
(BOS, CHoCH, FVG, EMA, RSI, ...) is used verbatim in all three; only the
connector words around it differ, and those are handled with a small
synonym table.

The parser's job is to extract STRUCTURE reliably. Anything it can't
confidently classify is kept as a "raw" condition and surfaced as
`warnings`/`missing` rather than silently guessed at -- the dashboard's
validation step is what turns that into a question back to the CEO.
"""

import re

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec

# [\s-]* (not just \s*) so common hyphenated phrasing ("1-minute",
# "5-minute", "15-minute chart") matches too, not just "1m"/"1 minute" --
# found via role-detection testing against real strategy text ("Entry
# Timeframe (1-minute): used to confirm reversal via BOS" was silently not
# matching at all, so a condition explicitly scoped to the entry timeframe
# in its own source text couldn't be detected).
_TIMEFRAME_RE = re.compile(r"\b(\d{1,3})[\s-]*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|week|weeks)\b", re.IGNORECASE)

_TIMEFRAME_FRAGMENT_STOPWORDS = {"on", "the", "at", "in", "chart", "timeframe", "tf", "candle", "of"}


def _is_bare_timeframe_fragment(seg_lower):
    """True for a segment that names a timeframe and nothing else of
    substance ("on the 1-minute chart") -- a connector fragment left over
    when a comma inside a reassembled numbered rule got treated as a
    condition separator, not a real independent rule."""
    m = _TIMEFRAME_RE.search(seg_lower)
    if not m:
        return False
    remainder = seg_lower[:m.start()] + seg_lower[m.end():]
    words = re.findall(r"[a-z]+", remainder)
    return all(w in _TIMEFRAME_FRAGMENT_STOPWORDS for w in words)


_UNIT_TO_SUFFIX = {
    "m": "m", "min": "m", "mins": "m", "minute": "m", "minutes": "m",
    "h": "h", "hr": "h", "hrs": "h", "hour": "h", "hours": "h",
    "d": "d", "day": "d", "days": "d",
    "w": "w", "week": "w", "weeks": "w",
}

_ROLE_KEYWORDS = {
    "bias": ["bias", "market bias", "daily bias", "higher timeframe", "htf"],
    "trend": ["trend"],
    "analysis": ["analysis", "structure", "structure tf", "intermediate"],
    "entry": ["entry", "entry tf", "entry timeframe", "ltf", "lower timeframe"],
    "confirmation": ["confirmation", "confirm", "trigger", "entry confirmation"],
}

_SECTION_KEYWORDS = {
    # long_entry_conditions/short_entry_conditions MUST be checked before the
    # generic entry_conditions below -- dict iteration order is insertion
    # order and _detect_section_header() returns on the first match, so
    # "Long Entry Rules:" (which also contains the substring "entry rule")
    # would otherwise match the generic entry_conditions bucket first.
    "long_entry_conditions": ["long entry rule", "long entry rules", "long entry:", "long entry condition", "long setup", "long rules", "long entry"],
    "short_entry_conditions": ["short entry rule", "short entry rules", "short entry:", "short entry condition", "short setup", "short rules", "short entry"],
    "entry_conditions": ["entry rule", "entry rules", "entry:", "entry condition", "entry conditions", "buy rule", "entry setup"],
    "exit_conditions": ["exit rule", "exit rules", "exit:", "exit condition", "exit conditions", "sell rule"],
    "confirmation_conditions": ["confirmation rule", "confirmation:", "confirmation condition", "trigger:"],
}

_CONCEPT_KEYWORDS = {
    # More specific PDH/PDL phrasings are listed before the bare "pdh"/"pdl"
    # keywords below so a segment like "sweep of PDL" matches pdl_sweep
    # first -- dict iteration order is insertion order, and the condition
    # loop below takes the first match, so ordering here is significant.
    "pdl_sweep": ["sweep of pdl", "pdl sweep", "pdl grab", "grab of pdl", "sweep of the pdl"],
    "pdh_sweep": ["sweep of pdh", "pdh sweep", "pdh grab", "grab of pdh", "sweep of the pdh"],
    "liquidity_sweep": ["liquidity sweep", "liquidity grab", "stop hunt", "sweep"],
    "bos": ["bos", "break of structure"],
    "choch": ["choch", "change of character"],
    "fvg": ["fvg", "fair value gap", "imbalance"],
    "order_block": ["order block", "orderblock", " ob "],
    "breaker_block": ["breaker block", "breaker"],
    "support": ["support"],
    "resistance": ["resistance"],
    "pdh": ["pdh", "previous day high", "prior day high"],
    "pdl": ["pdl", "previous day low", "prior day low"],
    "ema": ["ema"],
    "sma": ["sma"],
    "vwap": ["vwap"],
    "rsi": ["rsi"],
    "macd": ["macd"],
    "atr": ["atr"],
    "volume": ["volume"],
    # Engine-recognized concepts (backtest_engine.concepts / validator.
    # _KNOWN_INDICATORS) that were previously only reachable via the
    # AI-native path -- the plain-text parser had no keyword for them at
    # all, so text describing them (e.g. "a significant swing low")
    # silently fell through to an unexecutable type="raw" condition.
    # Added so both the parser's own text scan AND
    # repair_condition_roles() (which looks up this same table by
    # concept name) can recognize them.
    "candle_break": ["candle break", "trigger candle", "signal candle"],
    "swing_high": ["swing high", "significant high"],
    "swing_low": ["swing low", "significant low"],
    "session_high_low": ["session high", "session low"],
    "session_open": ["session open"],
    "poc": ["point of control", "poc"],
    "value_area": ["value area"],
    "lvn": ["low volume node", "lvn"],
    "hvn": ["high volume node", "hvn"],
    "aggression": ["aggressive candle", "aggression"],
    "mitigation_block": ["mitigation block", "mitigation"],
    "equal_highs_lows": ["equal highs", "equal lows"],
    "engulfing": ["engulfing"],
    "pin_bar": ["pin bar"],
    "inside_bar": ["inside bar"],
    "premium_discount_zone": ["premium zone", "discount zone", "premium and discount", "premium/discount"],
    "rejection_block": ["rejection block"],
    "orb": ["opening range breakout", "orb"],
    "initial_balance": ["initial balance"],
    "anchored_vwap": ["anchored vwap", "avwap"],
    "cvd": ["cumulative volume delta", "cvd"],
    "kill_zone": ["kill zone", "killzone", "kz"],
    "session_filter": ["session"],
    "trend_filter": ["trend filter", "with trend", "trend ke sath", "trend follow"],
}

_SESSION_NAMES = {
    "asian": ["asian session", "asia session", "tokyo session", "asian"],
    "london": ["london session", "london"],
    "ny": ["new york session", "ny session", "newyork", "new york", " ny "],
}

_DIRECTION_WORDS = {
    "bullish": ["bullish", "buy", "long", "upar", "upward", "up"],
    "bearish": ["bearish", "sell", "short", "neeche", "downward", "down"],
}

_ABOVE_WORDS = ["above", "upar", ">", "greater than", "crosses above"]
_BELOW_WORDS = ["below", "neeche", "<", "less than", "crosses below"]

# Public aliases -- the Knowledge Compiler's dictionary.py extends these
# tables rather than duplicating them, so a new alias added there can be
# rewritten into wording this parser already understands.
CONCEPT_KEYWORDS = _CONCEPT_KEYWORDS
SESSION_NAMES = _SESSION_NAMES
DIRECTION_WORDS = _DIRECTION_WORDS

_INDICATOR_WITH_PERIOD_RE = re.compile(
    r"\b(ema|sma|rsi|atr)\D{0,3}(\d{1,4})\b", re.IGNORECASE
)
_INDICATOR_COMPARE_RE = re.compile(
    r"\b(rsi|atr)\b.{0,15}?(<=|>=|<|>|below|neeche|above|upar)\s*(\d+(?:\.\d+)?)", re.IGNORECASE
)
_PRICE_VS_INDICATOR_RE = re.compile(
    r"\b(close|price)\b.{0,15}?(above|below|upar|neeche|>|<)\s*(ema|sma|vwap|pdh|pdl)\D{0,3}(\d{1,4})?", re.IGNORECASE
)
# One indicator compared to ANOTHER indicator (MA cross/alignment), e.g.
# "20-period EMA must be above the 50-period EMA" or "50 sma below 200 sma".
# Distinct from _INDICATOR_COMPARE_RE (indicator vs. a fixed number) and
# _PRICE_VS_INDICATOR_RE (price vs. an indicator) -- neither can represent
# this, which is why it silently fell through to an unexecutable type="raw"
# condition before this regex existed.
_INDICATOR_VS_INDICATOR_RE = re.compile(
    r"(\d{1,4})[\s-]*(?:period)?[\s-]*(ema|sma)\b.{0,25}?(above|below|greater than|less than|>|<)"
    r".{0,25}?(\d{1,4})[\s-]*(?:period)?[\s-]*(ema|sma)\b",
    re.IGNORECASE,
)

# Batch 11 -- URGENT: import was completely blocked because these
# directive regexes only accepted heavily abbreviated forms ("sl", "tp",
# a literal "%", a literal "rr"). Real pasted strategies (NotebookLM/
# ChatGPT output, plain English) spell things out: "stop loss", "take
# profit", "risk percent", "percent" instead of "%", "risk reward ratio
# N" instead of "RR N". Widened below to accept both the abbreviated and
# spelled-out forms, and gap tolerances (`.{0,N}?`) widened enough to
# span a connector word ("fixed", ":", "of") between the label and the
# value without becoming so wide it crosses into an unrelated directive
# on the same combined line.
_SL_LABEL = r"(?:stop[\s-]*loss|sl)\b"
_TP_LABEL = r"(?:take[\s-]*profit|tp)\b"
_PCT_UNIT = r"(?:%|percent\b|pct\b)"

# Negative lookahead excludes "risk reward"/"risk:reward"/"risk-reward"
# (an RR directive, handled separately by _match_rr) from ever being
# misread as a risk_pct label -- found live: "Take profit: risk reward
# ratio 4" was incorrectly setting risk_pct=4.0 before this guard existed,
# because "risk" is also the first word of that phrase.
_RISK_RE = re.compile(rf"\brisk\b(?!\s*[:\-]?\s*reward)\D{{0,20}}?(\d+(?:\.\d+)?)\s*(?:{_PCT_UNIT})?", re.IGNORECASE)

# RR is recognized in several independent forms; _match_rr() tries them in
# order (most-specific first) and returns the reward multiple per unit of
# risk, or None. A bare "A:B"/"A to B" ratio is accepted in either order
# ("1:3" and "3:1" both mean "risk 1 to make 3") since that's how traders
# actually write it -- the larger number is always the reward side.
_RR_RATIO_RE = re.compile(r"(?:\brr\b|risk\s*reward|r\s*:\s*r)\D{0,10}(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
# A bare "A:B" ratio on a Take Profit-labelled line ("Take profit: 1:4")
# with no "rr"/"risk reward" wording at all -- traders write the ratio
# alone under a TP label just as often as they spell out "risk reward".
_RR_TP_LABELED_RATIO_RE = re.compile(rf"{_TP_LABEL}\D{{0,10}}?(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_RR_SPOKEN_RE = re.compile(r"(?:\brr\b|risk\s*reward)\D{0,10}(\d+(?:\.\d+)?)\s*to\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
# "1 to 4 risk reward" -- the label comes AFTER the numbers, the mirror
# image of _RR_SPOKEN_RE above (label before numbers).
_RR_SPOKEN_SUFFIX_RE = re.compile(r"(\d+(?:\.\d+)?)\s*to\s*(\d+(?:\.\d+)?)\s*(?:risk\s*reward|rr)\b", re.IGNORECASE)
_RR_MINIMUM_RE = re.compile(r"minimum\s*(\d+(?:\.\d+)?)\s*(?:rr|risk\s*reward)?", re.IGNORECASE)
# "risk reward ratio 4" / "risk:reward 4" -- a label followed directly by
# a bare number, no colon-ratio and no "to". Tried before the fully bare
# "RR N"/"N R" forms below so a labelled line is never mistaken for an
# unrelated stray number.
_RR_LABELED_BARE_RE = re.compile(r"(?:risk\s*reward\s*ratio|risk\s*[:\-]?\s*reward|\brr\b)\D{0,15}?(\d+(?:\.\d+)?)\b", re.IGNORECASE)
_RR_BARE_RE = re.compile(r"\brr\b\D{0,5}(\d+(?:\.\d+)?)\b", re.IGNORECASE)
# "4R" -- a bare number immediately followed by a standalone "R". Tried
# last (most permissive, so checked only once nothing more specific
# matched) to avoid misreading an unrelated "R" elsewhere on the line.
_RR_MULTIPLE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*r\b", re.IGNORECASE)

# Percentage value near a label, accepting the number BEFORE the unit
# ("0.3%", "0.3 percent") or the unit-word BEFORE the number ("percent
# 0.3", "fixed percent 0.3") -- real pasted text uses both orders.
_PCT_VALUE_RE = re.compile(
    rf"(\d+(?:\.\d+)?)\s*{_PCT_UNIT}|(?:percent|pct)\s*(?:of\s*)?(\d+(?:\.\d+)?)\b", re.IGNORECASE
)


def _find_pct_near(label_re, text_lower, window=40):
    """Finds a percent value within `window` characters after the first
    match of `label_re` -- used for stop-loss/take-profit so a percentage
    elsewhere on an unrelated line never gets misattributed."""
    m = label_re.search(text_lower)
    if not m:
        return None
    segment = text_lower[m.end():m.end() + window]
    pm = _PCT_VALUE_RE.search(segment)
    if not pm:
        return None
    return float(pm.group(1) or pm.group(2))


_SL_ATR_RE = re.compile(rf"{_SL_LABEL}.{{0,20}}?(\d+(?:\.\d+)?)\s*(?:x\s*)?atr\b|atr\D{{0,10}}?(\d+(?:\.\d+)?)\D{{0,10}}?{_SL_LABEL}", re.IGNORECASE)
_SL_STRUCTURE_RE = re.compile(
    rf"{_SL_LABEL}.{{0,30}}?\b(order block|ob|swing|structure|breaker|fvg|fair value gap)\b", re.IGNORECASE
)
# "signal_candle" (Batch 3) -- the stop sits at the SIGNAL/TRIGGER bar's
# own high or low (a buffer % away), not a generic historical structure
# level -- e.g. "stop below the low of the candle that created the FVG",
# "stop below the FVG candle low", "SL above the signal candle high".
_SL_SIGNAL_CANDLE_RE = re.compile(
    r"\b(?:low|high)\s+of\s+(?:the\s+)?(?:signal|trigger|entry)\s+candle"
    r"|\b(?:signal|trigger)\s+candle\W{0,10}(?:low|high)\b"
    r"|\bcandle\s+that\s+(?:created|triggered|formed)\b.{0,20}\b(?:low|high)\b"
    r"|\b(?:low|high)\b.{0,20}\bcandle\s+that\s+(?:created|triggered|formed)\b",
    re.IGNORECASE,
)
_TP_LEVEL_RE = re.compile(rf"{_TP_LABEL}.{{0,20}}?\b(pdh|pdl)\b", re.IGNORECASE)

# Problem 2 (lookback window): a concept condition can require the concept
# to have occurred within the last N bars, not necessarily on the exact
# same bar as the other conditions in the same rule set -- real strategies
# are sequences ("sweep happens, THEN BOS, THEN FVG"), not everything
# lining up on one candle.
_LOOKBACK_WINDOW_RE = re.compile(r"\b(?:within|last|pichle)\s+(\d{1,3})\s*(?:bars?|candles?)\b", re.IGNORECASE)
_STRICT_SAME_BAR_RE = re.compile(r"\b(?:same\s*bar|same\s*candle|strict)\b", re.IGNORECASE)


def _match_rr(line_lower):
    """Recognizes RR as an explicit ratio ("1:3", "3:1", "2.5:1"), spoken
    ("1 to 3 risk reward", "risk reward 1 to 3"), "minimum N [RR]", a
    labelled bare number ("risk reward ratio 4", "risk:reward 4"), a bare
    "RR N", or a bare "4R". Tried in that order (most specific/least
    ambiguous first) so a labelled line is never mistaken for an
    unrelated stray number. Returns the reward multiple per unit of risk,
    or None if nothing matched."""
    for pattern in (_RR_RATIO_RE, _RR_TP_LABELED_RATIO_RE, _RR_SPOKEN_RE, _RR_SPOKEN_SUFFIX_RE):
        m = pattern.search(line_lower)
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            return (max(a, b) / min(a, b)) if min(a, b) else None
    m = _RR_MINIMUM_RE.search(line_lower)
    if m:
        return float(m.group(1))
    m = _RR_LABELED_BARE_RE.search(line_lower)
    if m:
        return float(m.group(1))
    m = _RR_BARE_RE.search(line_lower)
    if m:
        return float(m.group(1))
    m = _RR_MULTIPLE_RE.search(line_lower)
    if m:
        return float(m.group(1))
    return None


def _detect_lookback(seg_lower):
    """None means "use the evaluator's default window" (currently 10 bars);
    1 means strict same-bar (the original, pre-Phase-6 behavior); any other
    N is an explicit "within N bars"/"last N candles"/"pichle N candles"."""
    if _STRICT_SAME_BAR_RE.search(seg_lower):
        return 1
    m = _LOOKBACK_WINDOW_RE.search(seg_lower)
    if m:
        return int(m.group(1))
    return None


def _normalize_timeframe(number, unit):
    suffix = _UNIT_TO_SUFFIX.get(unit.lower())
    if suffix is None:
        return None
    return f"{number}{suffix}"


def _detect_role(line_lower):
    """A role LABEL only ever legitimately appears at the START of a line
    ("Entry: 15m", "Bias: 4H", "Entry timeframe on the 1H chart") -- never
    matched as a bare substring anywhere in the line. Batch 11: this was
    the field-routing bug's other half -- "below entry price" (inside a
    stop-loss line) and "Entry Rules: ... on the 1H chart" (a section
    header that also happens to mention a timeframe) both contain the
    substring "entry" NOT as a role label, and a naive `kw in line_lower`
    check misclassified both as bare "Entry:" role-hint lines, hijacking
    them away from stop-loss binding / section-header detection."""
    stripped = line_lower.strip()
    for role, keywords in _ROLE_KEYWORDS.items():
        for kw in keywords:
            if stripped == kw or stripped.startswith(kw + ":") or stripped.startswith(kw + " "):
                return role
    return None


_HTF_HINT_WORDS = ["higher timeframe", "htf"]


def _detect_condition_role(line_lower, timeframes):
    """Best-effort inline timeframe hint for a RULE line (e.g. "a
    significant low on the 1H or 4H chart" inside an Entry Rules line) --
    distinct from _detect_role(), which only recognizes a role LABEL
    ("Bias:", "Trend:") on its own line. Concept conditions were previously
    always evaluated on the entry timeframe no matter what the strategy
    text actually said (confirmed: "Liquidity Sweeps" describes swing
    highs/lows "on the 1H or 4H chart" but the engine only ever computed
    them on the 1-minute entry frame) -- this lets a rule line that
    unambiguously names one of the strategy's OWN already-declared
    non-entry timeframes tag its resulting Condition(s) with that role, so
    ConfiguredStrategy computes the concept on the real higher-timeframe
    data instead. `timeframes` is StrategyConfig.timeframes
    ({role: tf_string}); returns None (falls back to the entry-timeframe
    default, i.e. today's behavior) whenever nothing on the line
    unambiguously names an already-declared role -- never a guess. Can
    return "entry" too (e.g. a line that literally says "on the 1-minute
    chart" when entry=1m) -- functionally identical to None everywhere
    this is consumed (role or "entry" is the fallback throughout), but an
    explicit "entry" is more informative than a blank role wherever it's
    displayed (see the Strategies page's per-condition role tags)."""
    if not timeframes:
        return None
    for number, unit in _TIMEFRAME_RE.findall(line_lower):
        tf = _normalize_timeframe(number, unit)
        if not tf:
            continue
        for role, role_tf in timeframes.items():
            if role_tf == tf:
                return role
    if any(w in line_lower for w in _HTF_HINT_WORDS):
        for role in ("bias", "trend", "analysis"):
            if role in timeframes:
                return role
    return None


def _detect_section_header(line_lower):
    for section, keywords in _SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw in line_lower:
                return section
    return None


def _is_pure_timeframe_remainder(line):
    """True when the content after a line's first colon is JUST a
    timeframe mention ("Entry: 1m") with nothing else of substance --
    distinguishes a bare role/timeframe declaration from a rule-section
    header whose label happens to collide with the same keyword ("Entry
    Rules: bullish BOS on the 1H chart", where "1H" belongs to the rule
    text, not a timeframe declaration for the "entry" role)."""
    if ":" not in line:
        return False
    remainder = line.split(":", 1)[1].strip()
    if not remainder:
        return False
    m = _TIMEFRAME_RE.search(remainder)
    if not m:
        return False
    leftover = (remainder[:m.start()] + remainder[m.end():]).strip(" ,.-")
    return len(leftover) <= 3


def _detect_direction(text_lower):
    for direction, words in _DIRECTION_WORDS.items():
        for w in words:
            if w in text_lower:
                return direction
    return None


# ---------------------------------------------------------------- scaffolding stripping (Batch 11)
# Real pasted documents (NotebookLM/ChatGPT-style output the user actually
# pastes) are full of structural noise that is NEVER a trading rule: bare
# section headings ("RISK MANAGEMENT:", "FILTERS:", "Timeframes:"),
# "Source:"/citation attributions, "STEP N -- ..." headings, and numbered-
# list items whose continuation got split across raw lines by the
# document's own line wrapping. Stripped/reassembled here, BEFORE
# classification, so none of it can ever masquerade as an "unclear rule."

_STEP_HEADING_RE = re.compile(r"^step\s+\d+\s*[-–—:.]\s*", re.IGNORECASE)
_SOURCE_LINE_RE = re.compile(r"^(?:source|reference|citation|attribution)\s*:", re.IGNORECASE)
_NEW_ITEM_RE = re.compile(r"^(?:[-*•]|\d+[.)])\s+")
_SENTENCE_END_RE = re.compile(r"[.!?]\s*$")
# A line eligible to merge INTO the previous statement as a continuation:
# starts lowercase (a wrapped clause, "wait for a bullish engulfing
# candle") or is an orphaned parenthetical ("(opposite direction)"). A
# line starting uppercase/digit is a fresh sentence and must never merge,
# even if the previous line lacks trailing punctuation.
_CONTINUATION_START_RE = re.compile(r"^[a-z(]")


def _is_bare_heading(line):
    """A line whose ENTIRE content is a label -- nothing meaningful after
    the colon (e.g. "RISK MANAGEMENT:", "STOP LOSS:", "Timeframes:").
    Deliberately distinct from "Stop loss: fixed 0.3% below entry price",
    which has real content after the colon and must NOT be treated as
    scaffolding."""
    if ":" not in line:
        return False
    before, after = line.split(":", 1)
    return bool(before.strip()) and not after.strip()


def _is_meaningful_bare_heading(line_lower):
    """A bare heading the parser already knows what to DO with -- "Entry
    Rules:", "Bias:", "Confirmation:" etc -- must survive scaffolding
    stripping, since parse_strategy_text's own section/role detection
    depends on seeing it. Only a bare heading with NO recognized meaning
    ("RISK MANAGEMENT:", "FILTERS:", "STOP LOSS:", "Timeframes:" as a
    standalone label with the value elsewhere) is pure scaffolding."""
    return bool(_detect_section_header(line_lower) or _detect_role(line_lower))


def _strip_scaffolding_line(line):
    """Returns the line with document scaffolding removed, or None if the
    ENTIRE line is scaffolding and should be dropped outright. Never
    touches a line that carries real content, and never touches a bare
    heading the parser already has a real handler for -- only recognized
    structural noise with no meaning to this parser is discarded."""
    stripped = line.strip()
    if not stripped:
        return None
    if _SOURCE_LINE_RE.match(stripped):
        return None
    if _is_bare_heading(stripped) and not _is_meaningful_bare_heading(stripped.lower()):
        return None
    # "STEP 1 -- Identify the trend" keeps its real content ("Identify the
    # trend"), only the "STEP 1 --" scaffolding prefix is dropped -- a
    # STEP heading often carries the actual instruction on the same line.
    without_step = _STEP_HEADING_RE.sub("", stripped)
    return without_step if without_step.strip() else None


def _reassemble_lines(raw_lines):
    """Merges a soft-wrapped continuation back into the statement it
    belongs to, so a numbered/bulleted rule is always ONE rule regardless
    of how the source document wrapped its lines -- e.g. "4. On the
    1-minute chart," / "wait for a bullish engulfing candle" / "(opposite
    direction)" reassembles into one statement instead of three unrelated
    "unclear rule" fragments. A line starts a NEW statement only if it
    opens a new numbered/bulleted item, is itself a bare heading (handled
    separately by _strip_scaffolding_line), or the previous statement
    already looked grammatically complete (ended in . ! ?) -- otherwise
    it's treated as a continuation of whatever came before, including an
    orphaned parenthetical fragment like "opposite direction)". A line
    that starts with an uppercase letter (a fresh sentence, like "Enter
    on retracement into bullish FVG" following "Bullish BOS on the 1H
    chart" with no period between them) is never merged even when the
    previous line lacks trailing punctuation -- real pasted documents
    routinely omit end-of-line periods on genuinely separate rules, and
    merging them would silently fuse two conditions into one line, losing
    whichever concept the line-level condition parser doesn't match
    first. Only a line that itself reads as a continuation (starts
    lowercase, or an orphaned parenthetical) is eligible to merge."""
    merged = []
    for raw in raw_lines:
        line = _strip_scaffolding_line(raw)
        if line is None:
            continue
        # A "LABEL: value" line ("Stop loss: ...", "Entry Rules: ...") is
        # ALWAYS its own statement, regardless of whether the previous
        # line ended in sentence punctuation -- label:value lines are
        # extremely common in real strategy documents and essentially
        # never end in a period. Checked on a short PREFIX (not the whole
        # line) so a colon appearing later in a long sentence ("wait for
        # price to close: above the level") doesn't falsely count.
        has_early_label = ":" in line[:30] and bool(line[:30].split(":", 1)[0].strip())
        looks_like_new_sentence = bool(merged) and not _CONTINUATION_START_RE.match(line)
        starts_new = (
            bool(_NEW_ITEM_RE.match(line)) or _is_bare_heading(line) or has_early_label
            or not merged or looks_like_new_sentence
        )
        if not starts_new and merged and not _SENTENCE_END_RE.search(merged[-1]):
            merged[-1] = merged[-1].rstrip() + " " + line.lstrip()
        else:
            merged.append(line)
    return merged


def _parse_conditions_from_line(line, timeframes=None):
    """Split a rule line into atomic Condition objects. Anything that
    doesn't match a known pattern is kept verbatim as type="raw".

    `timeframes` (StrategyConfig.timeframes, optional) lets a concept
    condition inherit an inline higher-timeframe hint from the line itself
    (see _detect_condition_role) -- defaults to None so parse_conditions()
    below (used by the Knowledge Engine for lessons, which have no declared
    multi-timeframe roles) is completely unaffected."""
    # Strip a leading numbered/bulleted marker ("4. ") before splitting --
    # _reassemble_lines() keeps it so a numbered item survives as ONE
    # statement, but left in place it contaminates the first comma-split
    # segment ("4. On the 1-minute chart") into its own bogus fragment.
    line = _NEW_ITEM_RE.sub("", line, count=1)
    line_role = _detect_condition_role(line.lower(), timeframes)
    segments = re.split(r"\band\b|\baur\b|\+|,", line, flags=re.IGNORECASE)
    conditions = []

    for seg in segments:
        seg = seg.strip(" .")
        if not seg:
            continue
        seg_lower = seg.lower()
        matched = False

        m = _INDICATOR_VS_INDICATOR_RE.search(seg_lower)
        if m:
            op_word = m.group(3)
            op = ">" if op_word in (">", "above", "greater than") else "<"
            conditions.append(Condition(
                type="indicator_vs_indicator",
                indicator=m.group(2), params={"period": int(m.group(1))},
                op=op,
                indicator2=m.group(5), params2={"period": int(m.group(4))},
                role=line_role,
            ))
            matched = True

        if not matched:
            m = _PRICE_VS_INDICATOR_RE.search(seg_lower)
            if m:
                op_word = m.group(2)
                op = ">" if op_word in ("above", "upar", ">") else "<"
                params = {"period": int(m.group(4))} if m.group(4) else {}
                conditions.append(Condition(
                    type="price_compare", op=op, indicator=m.group(3), params=params,
                ))
                matched = True

        if not matched:
            m = _INDICATOR_COMPARE_RE.search(seg_lower)
            if m:
                op_word = m.group(2)
                op = {"below": "<", "neeche": "<", "above": ">", "upar": ">"}.get(op_word, op_word)
                conditions.append(Condition(
                    type="indicator_compare", indicator=m.group(1), op=op, value=float(m.group(3)),
                ))
                matched = True

        if not matched:
            for session, names in _SESSION_NAMES.items():
                if any(n in seg_lower for n in names):
                    conditions.append(Condition(type="session", name=session))
                    matched = True
                    break

        if not matched:
            for concept, keywords in _CONCEPT_KEYWORDS.items():
                if concept in ("session_filter",):
                    continue
                if any(kw in seg_lower for kw in keywords):
                    direction = _detect_direction(seg_lower)
                    lookback_bars = _detect_lookback(seg_lower)
                    conditions.append(Condition(
                        type="concept", name=concept, direction=direction, lookback_bars=lookback_bars,
                        role=line_role,
                    ))
                    matched = True
                    break

        if not matched and any(kw in seg_lower for kw in _CONCEPT_KEYWORDS["trend_filter"]):
            direction = _detect_direction(seg_lower) or "up"
            conditions.append(Condition(type="trend", direction=direction))
            matched = True

        if not matched:
            if _is_bare_timeframe_fragment(seg_lower):
                # A leftover connector fragment like "on the 1-minute
                # chart" -- the comma that split it off a longer
                # reassembled numbered item was ordinary prose punctuation,
                # not a rule separator. It carries no rule content of its
                # own (the timeframe it names is already captured wherever
                # the real condition/timeframe declaration bound it), so
                # silently dropping it is correct -- surfacing it as
                # "unclear" would just be structural noise, exactly what
                # Requirement 2/3 asked to eliminate.
                continue
            conditions.append(Condition(type="raw", text=seg))

    return conditions


def parse_conditions(text):
    """Public entry point to the same condition parser strategies use,
    reused by the Knowledge Engine to turn a lesson's free-text description
    into structured Condition objects."""
    return _parse_conditions_from_line(text)


def repair_condition_roles(config):
    """Deterministic post-processing repair for Condition.role, usable on
    ANY already-built StrategyConfig -- the AI-native import path (which
    doesn't reliably self-report role despite being asked to), or a
    one-time backfill pass over an already-saved strategy. Reuses the
    exact same role-detection logic (_detect_condition_role /
    _CONCEPT_KEYWORDS) the plain-text parser applies to itself while
    parsing line-by-line, just replayed against the strategy's own stored
    raw_text after the fact.

    For each concept condition that doesn't already have a role, finds
    the first raw_text line that mentions that concept (via the same
    keyword table _parse_conditions_from_line uses to recognize it in the
    first place) and runs the same inline-timeframe detection against
    that line. Never invents a role and never overwrites one that's
    already set -- only fills a gap, and only when the source text
    unambiguously names one of the strategy's own already-declared
    timeframes. A concept with no keyword table entry, or that never
    appears in raw_text, or whose line doesn't name a timeframe, is left
    exactly as it was (role stays None -- the entry-timeframe default,
    identical to today's behavior).

    Mutates `config` in place. Returns True if anything changed."""
    if not config.raw_text or not config.timeframes:
        return False
    lines = [ln for ln in config.raw_text.splitlines() if ln.strip()]
    changed = False
    all_buckets = [getattr(config, n) for n in
                   ("entry_conditions", "long_entry_conditions", "short_entry_conditions",
                    "exit_conditions", "confirmation_conditions")]
    all_buckets += [g.get("conditions") or [] for g in config.entry_rule_groups]
    for bucket in all_buckets:
        for cond in bucket:
            if cond.type not in ("concept", "indicator_vs_indicator") or cond.role or not (cond.name or cond.indicator):
                continue
            # indicator_vs_indicator has no `name` (it compares indicator to
            # indicator2, e.g. ema vs ema) -- look its keyword up by
            # `indicator` instead, same table either way.
            keywords = _CONCEPT_KEYWORDS.get(cond.name or cond.indicator)
            if not keywords:
                continue
            for line in lines:
                line_lower = line.lower()
                if not any(kw in line_lower for kw in keywords):
                    continue
                # Keep scanning subsequent mentions of the same concept
                # until one of them actually names a timeframe -- a
                # document often mentions a concept generically first
                # ("price sweeps the liquidity") and only states its
                # timeframe in a later line ("on the 1-minute chart,
                # BOS is confirmed after the sweep"); stopping at the
                # first (timeframe-less) mention would miss it.
                role = _detect_condition_role(line_lower, config.timeframes)
                if role:
                    cond.role = role
                    changed = True
                    break
    return changed


def _match_stop_loss(line_lower):
    """Tries every recognized stop-loss phrasing, most specific first, and
    returns an SLTPSpec or None. signal_candle (a natural-language-only
    form -- there's no abbreviated shorthand for it) is checked before the
    generic "structure" match since "the candle that created the FVG" also
    contains the word "fvg", which would otherwise match _SL_STRUCTURE_RE
    first and lose the more precise signal-candle semantics."""
    if _SL_SIGNAL_CANDLE_RE.search(line_lower):
        return SLTPSpec(type="signal_candle", value=None)
    pct = _find_pct_near(re.compile(_SL_LABEL, re.IGNORECASE), line_lower)
    if pct is not None:
        return SLTPSpec(type="fixed_pct", value=pct)
    m = _SL_ATR_RE.search(line_lower)
    if m:
        return SLTPSpec(type="atr_multiple", value=float(m.group(1) or m.group(2)))
    m = _SL_STRUCTURE_RE.search(line_lower)
    if m:
        return SLTPSpec(type="structure", value=None)
    return None


def _match_take_profit(line_lower):
    m = _TP_LEVEL_RE.search(line_lower)
    if m:
        return SLTPSpec(type="level", level=m.group(1).lower())
    pct = _find_pct_near(re.compile(_TP_LABEL, re.IGNORECASE), line_lower)
    if pct is not None:
        return SLTPSpec(type="fixed_pct", value=pct)
    return None


def parse_strategy_text(text, name="Unnamed Strategy"):
    config = StrategyConfig(name=name, raw_text=text)
    raw_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Batch 11: reassemble soft-wrapped continuations (a numbered/bulleted
    # rule split across raw lines by the source document's own line
    # wrapping) and drop pure document scaffolding (bare section headings,
    # "Source:" attributions, "STEP N --" prefixes) BEFORE any
    # classification happens, so none of it can end up as a fabricated
    # "unclear rule".
    lines = _reassemble_lines(raw_lines)

    current_section = None
    current_role_hint = None

    for line in lines:
        line_lower = line.lower()

        # Batch 11 -- URGENT FIX: Risk / RR / SL / TP directives are now
        # checked FIRST, before role/section/timeframe detection. This was
        # the field-routing bug's root cause: a line like "Stop loss:
        # fixed 0.3% below entry price" contains the substring "entry"
        # (inside "below entry price"), which _detect_role() matched as a
        # bare role-hint label -- the line was treated as an "Entry:"
        # declaration and `continue`d past BEFORE the stop-loss value was
        # ever looked at, then the same line later got swept up as a raw/
        # unclear entry condition by the generic fallback. Checking these
        # unambiguous, explicitly-labelled directives first means a
        # labelled field always binds to that field, never to entry
        # conditions, regardless of what other words happen to appear on
        # the same line. Each is checked independently (not a single if/
        # continue chain) so one compact line combining several directives
        # -- "SL 2% TP 4% Risk 1%" -- detects ALL of them.
        matched_directive = False

        m = _RISK_RE.search(line_lower)
        if m:
            config.risk_pct = float(m.group(1))
            matched_directive = True

        rr_value = _match_rr(line_lower)
        if rr_value is not None:
            config.risk_reward = rr_value
            matched_directive = True

        sl_spec = _match_stop_loss(line_lower)
        if sl_spec is not None:
            config.stop_loss = sl_spec
            matched_directive = True

        tp_spec = _match_take_profit(line_lower)
        if tp_spec is not None:
            config.take_profit = tp_spec
            matched_directive = True

        if matched_directive:
            current_role_hint = None
            continue

        # Concept/indicator mentions are recorded unconditionally so they're
        # never lost just because the line was also a timeframe/section
        # declaration (e.g. "Trend: 4H EMA 50"). Role is resolved from
        # *this* line first (e.g. "Trend" on "Trend: 4H EMA 50") before
        # falling back to whatever role the previous line set up --
        # otherwise the EMA would be tagged with the prior line's role.
        line_role = _detect_role(line_lower)
        effective_role_hint = line_role or current_role_hint

        for concept, keywords in _CONCEPT_KEYWORDS.items():
            if any(kw in line_lower for kw in keywords) and concept not in config.concepts_used:
                config.concepts_used.append(concept)
        for m in _INDICATOR_WITH_PERIOD_RE.finditer(line_lower):
            ind_name, period = m.group(1), int(m.group(2))
            config.indicators.append({
                "name": ind_name, "params": {"period": period}, "role": effective_role_hint,
            })

        # 1. timeframe declarations: "Entry: 15M" or a bare "Bias" label with
        #    the value on the next line. Checked before section headers
        #    since "entry:"/"confirmation:" alone are ambiguous with rule
        #    section names -- a timeframe pattern on the line resolves it.
        #    BUT only when this line isn't ALSO a real section header with
        #    real rule content ("Entry Rules: bullish BOS on the 1H
        #    chart") -- that "1H" belongs to the rule's own content, not a
        #    role-timeframe declaration, so section-header detection (more
        #    specific) must win whenever both could apply. Computed here,
        #    once, and reused below rather than calling twice.
        role = line_role
        section = _detect_section_header(line_lower)
        tf_matches = _TIMEFRAME_RE.findall(line)
        # A label like "Entry:" is itself ambiguous between a role/
        # timeframe declaration ("Entry: 1m") and a rule-section header
        # ("Entry Rules: ..." / "Entry: enter on retracement into the
        # FVG") -- both match _SECTION_KEYWORDS since "entry:" is listed
        # there too. The content AFTER the colon disambiguates: if it's
        # JUST the timeframe with nothing else of substance, it's a
        # timeframe declaration regardless of the section-name collision;
        # only real rule content after the colon lets section-header
        # detection (more specific) win.
        pure_tf_remainder = bool(tf_matches) and _is_pure_timeframe_remainder(line)
        if role and tf_matches and (not section or pure_tf_remainder):
            number, unit = tf_matches[0]
            tf = _normalize_timeframe(number, unit)
            if tf:
                config.timeframes[role] = tf
            current_role_hint = None
            continue
        elif tf_matches and current_role_hint and (not section or pure_tf_remainder):
            number, unit = tf_matches[0]
            tf = _normalize_timeframe(number, unit)
            if tf:
                config.timeframes[current_role_hint] = tf
            current_role_hint = None
            continue

        # 2. explicit rule-section headers ("Entry Rules:", "Confirmation
        #    Rules:", ...) -- more specific than a bare role keyword.
        if section:
            current_section = section
            current_role_hint = None
            after_colon = line.split(":", 1)
            remainder = after_colon[1].strip() if len(after_colon) > 1 else ""
            if remainder:
                getattr(config, section).extend(_parse_conditions_from_line(remainder, config.timeframes))
            continue

        if role:
            current_role_hint = role
            continue

        # 3. session directive
        if line_lower.startswith("session") or "session:" in line_lower:
            for session, names in _SESSION_NAMES.items():
                pattern = r"\b(" + "|".join(re.escape(n.strip()) for n in names) + r")\b"
                if re.search(pattern, line_lower) and session not in config.session_filter:
                    config.session_filter.append(session)
            current_role_hint = None
            continue

        if current_section:
            getattr(config, current_section).extend(_parse_conditions_from_line(line, config.timeframes))
        elif any(any(kw in line_lower for kw in kws) for kws in _CONCEPT_KEYWORDS.values()):
            config.entry_conditions.extend(_parse_conditions_from_line(line, config.timeframes))

    if config.take_profit.type == "unknown" and config.risk_reward is not None:
        config.take_profit = SLTPSpec(type="rr", value=config.risk_reward)

    _ensure_indicators_for_conditions(config)
    _fill_missing_and_warnings(config)
    return config


def _ensure_indicators_for_conditions(config):
    """An indicator only gets into config.indicators when it's mentioned
    with an explicit period (e.g. "EMA 50"). A condition like "RSI below
    40" references RSI without a period, so without this pass its column
    would never get computed. Backfill an entry for any indicator a
    condition needs but that was never declared -- keyed by
    (name, period, role) rather than just name, since indicator_vs_indicator
    needs the SAME name registered at two different periods (e.g. a 20 EMA
    and a 50 EMA) both present, not just whichever one was seen first."""
    def _key(ind):
        return (ind["name"], (ind.get("params") or {}).get("period"), ind.get("role"))

    existing = {_key(ind) for ind in config.indicators}

    def _ensure(name, params, role):
        if not name:
            return
        key = (name, (params or {}).get("period"), role)
        if key in existing:
            return
        config.indicators.append({"name": name, "params": dict(params or {}), "role": role})
        existing.add(key)

    all_buckets = [getattr(config, n) for n in
                   ("entry_conditions", "long_entry_conditions", "short_entry_conditions",
                    "exit_conditions", "confirmation_conditions")]
    all_buckets += [g.get("conditions") or [] for g in config.entry_rule_groups]
    for bucket in all_buckets:
        for cond in bucket:
            if cond.type in ("indicator_compare", "price_compare") and cond.indicator:
                # cond.role, not a hardcoded None -- _indicator_column()
                # resolves indicator_compare/price_compare columns using
                # the CONDITION's own role (exactly like it already does
                # for indicator_vs_indicator below), so backfilling under
                # role=None regardless of what the condition actually
                # declared registered a redundant, wrongly-tagged entry
                # instead of the one the evaluator will actually look up
                # first. Harmless when a name+period fallback match
                # exists (found live: EMA/Multi-Timeframe Trend-Pullback,
                # Daily High-Low Liquidity -- already-registered entries
                # under a real role still resolve correctly via that
                # fallback), but leaves a real gap when NO other entry
                # exists at all for that indicator (found live: Five A+
                # iFVG Setups' vwap was never declared under ANY role, so
                # "price < vwap" silently evaluated False on all 60,996
                # bars it was checked, forever).
                _ensure(cond.indicator, cond.params, cond.role)
            elif cond.type == "indicator_vs_indicator":
                _ensure(cond.indicator, cond.params, cond.role)
                _ensure(cond.indicator2, cond.params2, cond.role)


def _fill_missing_and_warnings(config):
    if "entry" not in config.timeframes:
        config.missing.append("entry timeframe")
    if not config.entry_conditions and not (config.long_entry_conditions or config.short_entry_conditions) and not config.entry_rule_groups:
        config.missing.append("entry rules")
    if not config.exit_conditions and config.stop_loss.type == "unknown":
        config.missing.append("exit rules (no exit conditions or stop-loss detected)")
    if config.stop_loss.type == "unknown":
        config.missing.append("stop loss")
    if config.take_profit.type == "unknown":
        config.missing.append("take profit")
    if config.risk_pct is None:
        config.missing.append("risk %")

    for bucket_name in ("entry_conditions", "long_entry_conditions", "short_entry_conditions",
                        "exit_conditions", "confirmation_conditions"):
        for cond in getattr(config, bucket_name):
            if cond.is_unclear():
                config.warnings.append(f"Unclear {bucket_name.replace('_', ' ')}: \"{cond.text}\"")
