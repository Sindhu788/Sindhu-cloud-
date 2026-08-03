"""Batch 5, Task 1 -- deterministic (no-AI) rule counting.

Pure code, costs nothing, never varies between runs on the same input.
This is the ground-truth checklist AI extraction is now measured
against, replacing the old AI-generated "rule inventory" call (which
itself could vary between runs on identical text -- exactly the kind of
non-determinism that made capture rates impossible to trust).

The approach is deliberately simple and over-inclusive: split the
document into individual statements, then flag any statement that LOOKS
like it could state a trading rule (conditional language, entry/exit/
stop/target terminology, a numeric threshold, a timeframe, or a
comparison). A false positive here (a statement flagged that isn't
really a rule) just costs one extra small AI call during sentence-level
extraction, which will correctly say "not a rule" -- cheap. A false
negative (a real rule never flagged) would silently vanish, which is
the actual failure mode Batch 3 documented, so the signal list below
errs toward catching too much rather than too little.
"""

import re

# ---------------------------------------------------------------- statement splitting

_LINE_SPLIT_RE = re.compile(r"[\r\n]+")
# Splits a paragraph into sentence-like chunks on '.', '!', '?', ';', or a
# bullet/numbering marker -- deliberately conservative (keeps decimal
# numbers like "0.15%" intact by requiring whitespace after the period).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9])")
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_MIN_STATEMENT_LEN = 8  # shorter than this is almost never a real rule (a title, a blank bullet, "Entry:")

# Real-world pasted documents (this project's users paste NotebookLM/AI-
# report-style markdown) are full of structural noise that is never a
# rule itself: markdown headings, table separator rows, and citation
# markers like "[1, 2]" that would otherwise trip the numeric signal
# below on a heading like "### 1. Strategy Profile".
_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s")
_TABLE_SEPARATOR_RE = re.compile(r"^\|?[\s:|-]+\|?$")
_CITATION_RE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
_TABLE_PIPES_RE = re.compile(r"\|")


def _strip_noise(line):
    line = _CITATION_RE.sub("", line)
    line = _TABLE_PIPES_RE.sub(" ", line)
    return re.sub(r"\s+", " ", line).strip()


def split_into_statements(text):
    """Deterministic, no AI. Returns a list of non-trivial statement
    strings -- one per line where a line contains one clause, or split
    further on sentence boundaries where a line bundles multiple clauses
    (common in pasted paragraph-style strategy descriptions). Markdown
    headings and table separator rows are dropped outright -- they are
    structural, never rule content."""
    if not text:
        return []
    statements = []
    for raw_line in _LINE_SPLIT_RE.split(text):
        stripped = raw_line.strip()
        if not stripped or _MARKDOWN_HEADING_RE.match(stripped) or _TABLE_SEPARATOR_RE.match(stripped):
            continue
        line = _strip_noise(_BULLET_PREFIX_RE.sub("", stripped))
        if not line:
            continue
        # A short line is almost always one clause already; only run the
        # sentence splitter on longer lines where multiple rules could be
        # bundled into one paragraph.
        if len(line) <= 140:
            candidates = [line]
        else:
            candidates = [s.strip() for s in _SENTENCE_SPLIT_RE.split(line) if s.strip()]
        for c in candidates:
            if len(c) >= _MIN_STATEMENT_LEN:
                statements.append(c)
    return statements


# ---------------------------------------------------------------- rule-candidate detection

_CONDITIONAL_WORDS = [
    "if ", "when ", "once ", "after ", "before ", "must ", "should ", "wait for",
    "only if", "as long as", "unless ", "provided that", "until ",
]
_ENTRY_EXIT_TERMS = [
    "entry", "enter", "exit", "close the trade", "stop loss", "stop-loss", " sl ", "sl:",
    "take profit", "take-profit", " tp ", "tp:", "target", "buy", "sell", "long", "short",
    "risk", "reward", "position size", "risk:reward", "risk-reward", "breakeven", "trailing",
]
_COMPARISON_TERMS = [
    ">", "<", ">=", "<=", "above", "below", "greater than", "less than",
    "crosses", "cross above", "cross below", "breaks above", "breaks below",
    "between", "at least", "no more than", "no less than",
]
# A number that actually looks like a trading parameter -- a percentage, a
# pip/point/R-multiple distance, or an explicit N-candle/N-bar/N-minute/
# N-hour count. Deliberately NOT "any digit" (a bare "1." from a markdown
# list/heading number is noise, not a rule) -- see split_into_statements,
# which already strips headings, but numbered body text like "Step 2:
# wait for..." can still reach here, and the bare "2" there carries no
# signal on its own; the surrounding entry_exit/conditional/comparison
# terms are what actually flag that kind of line.
_NUMERIC_RE = re.compile(
    r"\d+(\.\d+)?\s*%"                                   # 0.15%, 3%
    r"|\d+(\.\d+)?\s*(pip|point|r\b)"                    # 20 pips, 2R
    r"|\d+\s*-?\s*(m|min|minute|h|hr|hour|d|day|w|week)s?\b"  # 15m, 4-hour, 1 day
    r"|\d+\s*(candle|bar|tick)s?\b",                      # 3 candles, 2 bars
    re.IGNORECASE,
)

_ALL_SIGNAL_GROUPS = {
    "conditional": _CONDITIONAL_WORDS,
    "entry_exit": _ENTRY_EXIT_TERMS,
    "comparison": _COMPARISON_TERMS,
}


def _signals_in(statement):
    """Returns the set of signal group names this statement matched --
    used both to decide candidacy and, when useful, to explain why."""
    lower = statement.lower()
    hits = set()
    for group, terms in _ALL_SIGNAL_GROUPS.items():
        if any(term in lower for term in terms):
            hits.add(group)
    if _NUMERIC_RE.search(statement):
        hits.add("numeric_or_timeframe")
    return hits


def is_rule_candidate(statement):
    """A statement is a rule candidate if it shows at least one concrete
    signal of executable content (conditional language, entry/exit/risk
    terminology, a timeframe, a comparison, or a number) -- pure
    substring/regex matching, no AI, fully deterministic."""
    return bool(_signals_in(statement))


def count_candidate_rules(text):
    """The deterministic ground-truth checklist. Returns
    {"count": int, "candidates": [{"id": int, "text": str, "signals": [str, ...]}]}.
    `id` is stable for a given input (position in the filtered list), used
    to match this checklist against sentence-level extraction results."""
    statements = split_into_statements(text)
    candidates = []
    for i, s in enumerate(statements):
        signals = _signals_in(s)
        if signals:
            candidates.append({"id": len(candidates) + 1, "text": s, "signals": sorted(signals)})
    return {"count": len(candidates), "candidates": candidates}
