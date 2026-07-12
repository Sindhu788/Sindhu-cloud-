"""Rule Extractor -- routes the sections of a compiled document that
contain executable trading rules through the SAME bilingual parser
strategies have always used (backtest_engine.strategy_parser), after
running the text through the Knowledge Compiler's dictionary normalizer so
aliases the parser wouldn't otherwise recognize (e.g. "PDH", "demand zone",
"bullish OB") get rewritten into wording it already understands.

This is a routing + normalization layer only -- condition/timeframe/SL/TP
parsing itself is never reimplemented here.
"""

import re

from backtest_engine.strategy_parser import parse_strategy_text
from knowledge_compiler import dictionary
from knowledge_compiler import sections as sections_mod

# strategy_parser.parse_strategy_text checks SL/TP/RR/Risk regexes in a
# fixed order and `continue`s after the first hit -- a compact real-world
# line like "SL 2% TP 4% Risk 1%" only ever yields the first directive
# ("Risk"). Splitting each directive onto its own line before handoff fixes
# this without touching the underlying parser's regex logic at all.
_DIRECTIVE_WORD_RE = re.compile(r"\b(sl|tp|rr|risk)\b", re.IGNORECASE)

# strategy_parser's SL/TP regexes only recognize the abbreviations "sl"/"tp"
# (\bsl\b / \btp\b) -- spelled-out wording common in transcripts/reports
# ("stop loss goes below...", "take profit at...") never matches them at
# all. Expanding to the abbreviation first is a text-level fix, not a
# regex change to the underlying parser.
_SPELLED_OUT_SUBS = [
    (re.compile(r"\bstop\s*loss\b", re.IGNORECASE), "SL"),
    (re.compile(r"\btake\s*profit\b", re.IGNORECASE), "TP"),
]

# Spoken-style risk:reward ("1 to 3 risk reward", "1 to 3 RR") never matches
# strategy_parser's _RR_RE, which requires literal "1:3" colon notation.
_SPOKEN_RR_RE = re.compile(r"\b(\d+)\s*to\s*(\d+)\s*(risk\s*reward|rr)\b", re.IGNORECASE)


def _normalize_spoken_phrasing(text):
    for pattern, repl in _SPELLED_OUT_SUBS:
        text = pattern.sub(repl, text)
    return _SPOKEN_RR_RE.sub(lambda m: f"risk reward {m.group(1)}:{m.group(2)}", text)


def _split_combined_directives(text):
    out_lines = []
    for line in text.splitlines():
        matches = list(_DIRECTIVE_WORD_RE.finditer(line))
        if len(matches) <= 1:
            out_lines.append(line)
            continue
        last = 0
        for m in matches[1:]:
            out_lines.append(line[last:m.start()].rstrip())
            last = m.start()
        out_lines.append(line[last:])
    return "\n".join(ln for ln in out_lines if ln.strip())


def extract_strategy(text, name="Unnamed Strategy", detected_sections=None):
    """Returns a StrategyConfig built from the strategy-relevant sections of
    `text`. If detected_sections is None, sections are (re)detected here."""
    detected_sections = (
        detected_sections if detected_sections is not None else sections_mod.detect_sections(text)
    )
    relevant = sections_mod.sections_for_rules(detected_sections)

    if not relevant:
        combined = text
    else:
        parts = []
        for sec in relevant:
            # Only re-emit the heading text for section kinds
            # strategy_parser's own _SECTION_KEYWORDS actually recognizes
            # as a boundary (entry/exit rules). For every other kind
            # (Risk, Filters, Market Conditions, Checklist, ...) the parser
            # has no matching header keyword, so injecting that heading as
            # a bare text line would just get scanned as a regular
            # condition line under whatever section was last recognized --
            # e.g. a literal "Filters:" line ending up as a bogus "unclear
            # exit rule". Its body text is still included either way.
            if sec.heading and sec.kind in (sections_mod.ENTRY_RULES, sections_mod.EXIT_RULES):
                parts.append(sec.heading + ":")
            parts.append(sec.text)
        combined = "\n".join(parts)

    inline_extra = [ln for ln in sections_mod.inline_if_then_lines(text) if ln not in combined]
    if inline_extra:
        combined += "\n" + "\n".join(inline_extra)

    combined = _normalize_spoken_phrasing(combined)
    normalized = dictionary.normalize_text(_split_combined_directives(combined))
    return parse_strategy_text(normalized, name=name)
