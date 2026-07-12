"""Section detector -- splits a pasted document into labelled sections
(Summary, Entry Rules, Exit Rules, Risk, Market Conditions, Indicators,
Filters, Psychology, Common Mistakes, Weaknesses, Strengths, Checklist,
Pseudocode, IF-THEN Rules, Performance) so the Rule Extractor and Lesson
Extractor each only see the part of the document relevant to them, instead
of scanning the whole thing blindly.

Detects markdown headers (#/##), bold headers (**Entry Rules**), and short
colon-terminated headers ("Entry Rules:"). A document with no headers at
all (today's typical pasted strategy) falls back to one "body" section
covering the whole text -- fully backward compatible with the existing
flat parse_strategy_text() behavior.
"""

import re
from dataclasses import dataclass, field

SUMMARY = "summary"
ENTRY_RULES = "entry_rules"
EXIT_RULES = "exit_rules"
RISK = "risk"
MARKET_CONDITIONS = "market_conditions"
INDICATORS = "indicators"
FILTERS = "filters"
PSYCHOLOGY = "psychology"
COMMON_MISTAKES = "common_mistakes"
WEAKNESSES = "weaknesses"
STRENGTHS = "strengths"
CHECKLIST = "checklist"
PSEUDOCODE = "pseudocode"
IF_THEN_RULES = "if_then_rules"
PERFORMANCE = "performance"
BODY = "body"             # no header detected yet / leading text
NARRATIVE = "narrative"    # header detected but not a recognized kind -- ignored by extractors

# Sections whose content is fed to the Rule Extractor (executable strategy rules).
STRATEGY_SECTION_KINDS = {
    ENTRY_RULES, EXIT_RULES, RISK, MARKET_CONDITIONS, INDICATORS, FILTERS,
    CHECKLIST, PSEUDOCODE, IF_THEN_RULES, BODY,
}
# Sections whose content is fed to the Lesson Extractor (educational content).
LESSON_SECTION_KINDS = {
    SUMMARY, PSYCHOLOGY, COMMON_MISTAKES, WEAKNESSES, STRENGTHS, CHECKLIST,
    RISK, PERFORMANCE, BODY,
}

_HEADER_KEYWORDS = {
    SUMMARY: ["summary", "overview", "tldr", "tl;dr", "introduction"],
    ENTRY_RULES: ["entry rule", "entry rules", "entry condition", "entry conditions", "entry setup", "entry criteria", "how to enter", "buy rule", "buy setup"],
    EXIT_RULES: ["exit rule", "exit rules", "exit condition", "exit conditions", "how to exit", "sell rule"],
    RISK: ["risk management", "risk rules", "money management", "position sizing", "risk:"],
    MARKET_CONDITIONS: ["market condition", "market conditions", "market state", "market type", "when to trade", "market environment"],
    INDICATORS: ["indicator", "indicators", "indicators used", "tools used"],
    FILTERS: ["filter", "filters", "confirmation filter", "confirmation filters"],
    PSYCHOLOGY: ["psychology", "mindset", "emotions", "trading psychology", "mental game"],
    COMMON_MISTAKES: ["common mistake", "common mistakes", "mistakes", "pitfalls", "errors to avoid"],
    WEAKNESSES: ["weakness", "weaknesses", "limitation", "limitations", "drawback", "drawbacks", "cons"],
    STRENGTHS: ["strength", "strengths", "advantage", "advantages", "pros"],
    CHECKLIST: ["checklist", "pre-trade checklist", "steps"],
    PSEUDOCODE: ["pseudocode", "pseudo code", "algorithm", "logic"],
    IF_THEN_RULES: ["if-then", "if then rule", "if then rules"],
    PERFORMANCE: ["performance", "results", "backtest results", "win rate", "statistics"],
}

_MD_HEADER_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*$")
_BOLD_HEADER_RE = re.compile(r"^\*\*\s*(.+?)\s*\*\*:?\s*$")
_COLON_HEADER_RE = re.compile(r"^([A-Za-z][A-Za-z /&\-]{2,40}):\s*$")
_IF_THEN_LINE_RE = re.compile(r"^\s*(if|agar)\b.{0,80}\b(then|to)\b", re.IGNORECASE)
_TITLE_LINE_RE = re.compile(r"^\s*#{0,6}\s*\**\s*(strategy name|strategy|title|name)\s*:\s*(.+?)\s*\**\s*$", re.IGNORECASE)


def extract_title(text):
    """If the very first non-blank line looks like a title/name declaration
    ("Strategy Name: EMA Pullback Long", "Title: ..."), pull it out as
    document metadata and strip it from the working text. Without this, a
    strategy's own title can get accidentally scanned as a rule line before
    any real section header appears -- e.g. "...Pullback Long" reads as a
    bullish direction hint to the concept-keyword fallback in
    strategy_parser.parse_strategy_text. Returns (title_or_None, remaining_text).
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        m = _TITLE_LINE_RE.match(line)
        if m:
            remaining = "\n".join(lines[:i] + lines[i + 1:])
            return m.group(2).strip(), remaining
        break  # only the very first non-blank line is ever considered a title
    return None, text


@dataclass
class Section:
    kind: str
    heading: str
    text: str
    start_line: int
    end_line: int

    def to_dict(self):
        return {"kind": self.kind, "heading": self.heading, "line_count": self.end_line - self.start_line + 1}


def _header_kind(heading_text):
    lower = heading_text.strip().lower().rstrip(":")
    for kind, keywords in _HEADER_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return kind
    return None


def _match_header(line):
    """Returns (heading_text, matched) if `line` looks like a section header."""
    m = _MD_HEADER_RE.match(line)
    if m:
        return m.group(1), True
    m = _BOLD_HEADER_RE.match(line)
    if m:
        return m.group(1), True
    m = _COLON_HEADER_RE.match(line)
    if m and len(m.group(1).split()) <= 6:
        return m.group(1), True
    return None, False


def detect_sections(text):
    """Returns a list of Section objects covering the whole document in
    order. Guaranteed non-empty for any non-blank input."""
    lines = text.splitlines()
    sections = []
    current_kind, current_heading = BODY, ""
    current_lines = []
    current_start = 0

    def flush(end_line):
        if current_lines and any(ln.strip() for ln in current_lines):
            sections.append(Section(current_kind, current_heading, "\n".join(current_lines), current_start, end_line))

    for i, line in enumerate(lines):
        heading_text, is_header = _match_header(line)
        if is_header:
            flush(i - 1)
            kind = _header_kind(heading_text)
            current_kind = kind or NARRATIVE
            current_heading = heading_text.strip()
            current_lines = []
            current_start = i + 1
            continue
        current_lines.append(line)

    flush(len(lines) - 1)

    if not sections:
        sections.append(Section(BODY, "", text, 0, len(lines) - 1))

    return sections


def inline_if_then_lines(text):
    """IF-THEN / pseudocode style lines can appear anywhere, not just under
    an explicit header -- collected separately so the Rule/Lesson extractors
    can still see them even in an unheaded document."""
    return [ln.strip() for ln in text.splitlines() if _IF_THEN_LINE_RE.match(ln)]


def sections_for_rules(sections):
    return [s for s in sections if s.kind in STRATEGY_SECTION_KINDS]


def sections_for_lessons(sections):
    return [s for s in sections if s.kind in LESSON_SECTION_KINDS]
