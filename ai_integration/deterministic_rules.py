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
# Extraction Pipeline Improvements (gap 2): a session-scoping statement
# ("Trades only during the New York session") has no entry/exit/
# conditional/numeric/comparison term at all, so it was previously
# invisible to is_rule_candidate and never even reached the AI to have
# session_filter populated -- silently dropped before extraction, not
# during it. This signal group exists purely to catch that phrasing.
_SESSION_TERMS = [
    "session", "new york session", "ny session", "london session",
    "asian session", "london open", "ny open", "new york open",
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
    "session": _SESSION_TERMS,
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


_PREAMBLE_MAX_CHARS = 700
_PREAMBLE_MAX_STATEMENTS = 6
# A section whose heading suggests the document's actual RULES have
# started -- the preamble must never reach into these, since it exists
# only to carry OPENING/setup context, not the rules a statement is
# itself being judged against.
_RULE_SECTION_KEYWORDS = ("entry", "exit", "stop loss", "stop-loss", "take profit", "take-profit")


def extract_document_preambles(text):
    """Two-Focused-Day Push, Part 1 -- a short, deterministic (no AI)
    summary of the document's OWN opening statements (the overview
    sentence plus whatever "Setup/Preparation"-style content precedes the
    first Entry/Exit/Stop-Loss section), capped at _PREAMBLE_MAX_CHARS /
    _PREAMBLE_MAX_STATEMENTS, whichever comes first.

    Real strategy documents commonly define named references up front
    ("identify the most recent Fractal high and Fractal low... to create
    your trading range") that LATER statements then refer back to only by
    a short name ("the marked 4H high level") -- in isolation, a later
    statement has no way to know what that name means. Giving every
    isolated per-statement AI call this same short preamble (general,
    since almost every real document opens with exactly this kind of
    setup/definition content, not hand-tuned to any one document) lets it
    resolve that backward reference instead of falling back to type="raw"
    for lack of context.

    Returns {model_label_or_None: preamble_text}. For a single-model
    document this is always {None: "..."}. For a multi-model document, one
    PREAMBLE PER MODEL, built only from THAT model's own opening
    statements -- never blending Model 2's content into a preamble handed
    to a Model 1 statement (or vice-versa), which would silently undo Gap
    1's model-separation fix. A model with no useful opening content maps
    to ""."""
    if not text:
        return {None: ""}
    labeled = split_into_statements_with_labels(text)
    if not labeled:
        return {None: ""}
    model_labels = sorted({m for _t, m, _s in labeled}, key=lambda x: (x is None, x)) or [None]
    preambles = {}
    for target_model in model_labels:
        parts, total = [], 0
        for statement_text, model_label, section_label in labeled:
            if model_label != target_model:
                continue
            if section_label and any(k in section_label.lower() for k in _RULE_SECTION_KEYWORDS):
                break
            # A statement carrying its own "session" or "entry_exit"
            # signal is a complete, standalone rule in its own right (it
            # already gets its own separate AI call) -- never folded into
            # a SIBLING statement's background context, which would make
            # an isolated statement look like it's partly about a
            # different rule entirely. Only genuinely descriptive/setup
            # content (numeric/timeframe mentions, plain prose) becomes
            # preamble.
            if _signals_in(statement_text) & {"session", "entry_exit"}:
                continue
            parts.append(statement_text)
            total += len(statement_text)
            if total >= _PREAMBLE_MAX_CHARS or len(parts) >= _PREAMBLE_MAX_STATEMENTS:
                break
        preambles[target_model] = " ".join(parts).strip()[:_PREAMBLE_MAX_CHARS]
    return preambles


def count_candidate_rules(text):
    """The deterministic ground-truth checklist. Returns
    {"count": int, "candidates": [{"id": int, "text": str, "signals": [str, ...],
    "model_label": str|None, "section_label": str|None}]}.
    `id` is stable for a given input (position in the filtered list), used
    to match this checklist against sentence-level extraction results.

    `model_label` (Extraction Pipeline Improvements, gap 1) tags each
    candidate with the distinct trading model/setup heading it falls
    under, if any -- see split_into_statements_with_labels below. None for
    a single-model document (unchanged behavior for every strategy that
    predates this feature).

    `section_label` (Two-Focused-Day Push, Part 1) tags each candidate
    with the nearest ANY-level structural heading above it -- populated
    for every document that has section headings, not just multi-model
    ones. Purely informational, passed to the AI as light disambiguating
    context; never used for routing."""
    labeled = split_into_statements_with_labels(text)
    candidates = []
    for text_, model_label, section_label in labeled:
        signals = _signals_in(text_)
        if signals:
            candidates.append({
                "id": len(candidates) + 1, "text": text_, "signals": sorted(signals),
                "model_label": model_label, "section_label": section_label,
            })
    return {"count": len(candidates), "candidates": candidates}


# ---------------------------------------------------------------- multi-model detection
#
# Extraction Pipeline Improvements (gap 1): a source document sometimes
# describes TWO OR MORE genuinely distinct trading models (e.g. "Model 1:
# The Trend Following Model" ... "Model 2: The Mean Reverting Model"),
# each with its own entry/exit/session rules -- split_into_statements
# above discards markdown headings outright as pure structural noise,
# which is right for statement extraction but means the heading text
# ("Model 1: ...") that would identify WHICH model a later statement
# belongs to is thrown away before anything downstream ever sees it.
# This section recovers that heading structure deterministically, no AI,
# so sentence_level_extraction can tag each statement with the model it
# falls under instead of flattening everything into one merged setup.
_MODEL_HEADING_RE = re.compile(
    r"^(model|setup|strategy)\s*#?\s*(\d+)\b\s*[:\-]?\s*(.*)$", re.IGNORECASE,
)
# A heading line survives markdown noise (###, **bold**, trailing **) that
# would otherwise stop the pattern above from matching the leading word.
_HEADING_MARKDOWN_STRIP_RE = re.compile(r"^#{1,6}\s*|\*{1,3}|:{0,1}\s*$")
# A bare in-body mention (not a heading) of "model 2"/"setup 3" etc. --
# used only to flag ambiguity when such language exists WITHOUT a clean
# heading to anchor it, never to silently guess a label.
_MODEL_MENTION_RE = re.compile(r"\b(model|setup|strategy)\s*#?\s*(\d+)\b", re.IGNORECASE)


def _clean_heading_line(raw_line):
    stripped = raw_line.strip()
    if not _MARKDOWN_HEADING_RE.match(stripped) and "**" not in stripped:
        return None
    cleaned = _HEADING_MARKDOWN_STRIP_RE.sub("", stripped).strip()
    cleaned = _HEADING_MARKDOWN_STRIP_RE.sub("", cleaned).strip()  # bold can wrap both ends
    return cleaned or None


def detect_model_sections(text):
    """Scans for "Model N:"/"Setup N:"/"Strategy N:" style headings (markdown
    heading lines, optionally bold) and returns:
    {"labels": ["Model 1: The Trend Following Model", ...], "ambiguous": bool,
     "reason": str|None}.

    `labels` is empty for an ordinary single-model document (the common
    case, byte-identical behavior to before this feature). `ambiguous` is
    True only when the text clearly TALKS ABOUT multiple numbered models/
    setups in body text but fewer than 2 of them have a clean heading to
    anchor a confident split -- this is a signal to flag for clarification
    rather than silently guess which statements belong to which model."""
    if not text:
        return {"labels": [], "ambiguous": False, "reason": None}
    labels = []
    for raw_line in _LINE_SPLIT_RE.split(text):
        cleaned = _clean_heading_line(raw_line)
        if not cleaned:
            continue
        m = _MODEL_HEADING_RE.match(cleaned)
        if m:
            label = cleaned.strip()
            if label not in labels:
                labels.append(label)

    mentions = {m.group(2) for m in _MODEL_MENTION_RE.finditer(text)}
    if len(labels) >= 2:
        return {"labels": labels, "ambiguous": False, "reason": None}
    if len(mentions) >= 2:
        return {
            "labels": labels, "ambiguous": True,
            "reason": (
                f"Document mentions {len(mentions)} numbered models/setups in its "
                "text but fewer than 2 have a clear heading to confidently separate "
                "them -- needs clarification rather than a guess."
            ),
        }
    return {"labels": [], "ambiguous": False, "reason": None}


_HEADING_NUMBER_PREFIX_RE = re.compile(r"^\d+\.\s*")
# A short line ENTIRELY wrapped in bold markers, with nothing outside them
# ("**Margin Buffer:**", "**Short Entry (Sell)**") -- a section label, not
# a rule. Deliberately narrow: a long bold SENTENCE that merely contains
# emphasis somewhere in the middle ("A valid sweep should ideally occur
# with **strong candles**.") does NOT match this, since removing the bold
# markers there still leaves real rule content, not scaffolding.
_BOLD_ONLY_LINE_RE = re.compile(r"^\*\*[^*]+\*\*:?$")


def _is_bold_only_heading_line(stripped_line):
    return bool(_BOLD_ONLY_LINE_RE.match(stripped_line))


def _clean_section_heading_line(raw_line):
    """Like _clean_heading_line, but for ANY structural heading -- a
    markdown '#'-level heading, or a bold-only section-label line, with or
    without a leading bullet marker ("*   **Placement:**") -- not just the
    "Model N:" pattern _clean_heading_line's caller looks for. Returns the
    cleaned, human-readable heading text, or None if this line isn't a
    heading at all. A leading ordinal ("1. ", "2. ") is stripped too,
    since that numbering is scaffolding, not the section's real name."""
    stripped = raw_line.strip()
    unbulleted = _BULLET_PREFIX_RE.sub("", stripped).strip()
    if not _MARKDOWN_HEADING_RE.match(stripped) and not _is_bold_only_heading_line(unbulleted):
        return None
    cleaned = _HEADING_MARKDOWN_STRIP_RE.sub("", unbulleted).strip()
    cleaned = _HEADING_MARKDOWN_STRIP_RE.sub("", cleaned).strip()
    cleaned = _HEADING_NUMBER_PREFIX_RE.sub("", cleaned).strip()
    return cleaned or None


def split_into_statements_with_labels(text):
    """Same statement splitting as split_into_statements, but each
    statement is paired with (model_label, section_label):

    - model_label: the "Model N:"/"Setup N:" heading it falls under, or
      None. Only populated when the document has 2+ confidently-detected
      model headings (unchanged from before this function grew a second
      label) -- drives entry_rule_groups ROUTING (Gap 1), a structural
      decision, so it stays deliberately conservative.
    - section_label: the nearest ANY-level structural heading above this
      statement (e.g. "Short Entry (Sell)", "Stop Loss (SL) Rules"),
      whether or not the document is multi-model. Purely informational
      CONTEXT passed to the AI call (see sentence_level_extraction.py) so
      an isolated statement that backward-references something defined
      earlier in the same section ("the marked 4H high level") has a
      fighting chance of being resolved instead of falling back to
      type="raw" for lack of context -- never used for routing, so a
      wrong/coarse section_label can only miss a hint, never misfile a
      condition into the wrong entry_rule_group.

    Returns [(statement_text, model_label_or_None, section_label_or_None), ...].
    """
    if not text:
        return []
    sections = detect_model_sections(text)
    multi_model = len(sections["labels"]) >= 2
    current_model_label = None
    current_section_label = None
    out = []
    for raw_line in _LINE_SPLIT_RE.split(text):
        stripped = raw_line.strip()
        if not stripped:
            continue
        if multi_model:
            cleaned = _clean_heading_line(stripped)
            if cleaned:
                m = _MODEL_HEADING_RE.match(cleaned)
                if m and cleaned in sections["labels"]:
                    current_model_label = cleaned
        section_cleaned = _clean_section_heading_line(stripped)
        if section_cleaned:
            current_section_label = section_cleaned
        if not stripped or _MARKDOWN_HEADING_RE.match(stripped) or _TABLE_SEPARATOR_RE.match(stripped):
            continue
        # A bold-only line ("**Placement:**") IS a section label (recorded
        # above) AND pure structural scaffolding, never rule content on
        # its own -- skip it as a statement candidate the same way a '#'
        # heading already is, instead of also trying to extract a rule
        # from "Placement:". A bullet-prefixed bold-only line ("*
        # **Placement:**") still counts -- the bullet marker itself isn't
        # what makes a line a heading vs. content.
        if _is_bold_only_heading_line(_BULLET_PREFIX_RE.sub("", stripped).strip()):
            continue
        line = _strip_noise(_BULLET_PREFIX_RE.sub("", stripped))
        if not line:
            continue
        if len(line) <= 140:
            candidates = [line]
        else:
            candidates = [s.strip() for s in _SENTENCE_SPLIT_RE.split(line) if s.strip()]
        for c in candidates:
            if len(c) >= _MIN_STATEMENT_LEN:
                out.append((c, current_model_label if multi_model else None, current_section_label))
    return out
