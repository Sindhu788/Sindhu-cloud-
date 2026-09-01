"""Item 7 (Cross-Reference Validation) -- deterministic, AI-free extraction
of a source document's OWN performance claims (e.g. "wins 60% of the
time", "70% win rate"), captured verbatim at import time so they can later
be compared against this strategy's real, measured backtest result (see
backtest_engine.claim_validation.compare_claim_to_backtest) instead of
being silently trusted. A regex scan is enough for this pattern -- no AI
call needed, so this runs free on every import regardless of AI
availability or Groq rate limits."""

import re

_WIN_RATE_PATTERNS = [
    re.compile(r"wins?\s+(?:approximately\s+|about\s+|around\s+)?(\d{1,3}(?:\.\d+)?)\s*%\s+of\s+(?:the\s+)?(?:time|trades)", re.I),
    re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%\s+win[\s-]?rate", re.I),
    re.compile(r"win[\s-]?rate\s+(?:of\s+)?(?:approximately\s+|about\s+|around\s+)?(\d{1,3}(?:\.\d+)?)\s*%", re.I),
    re.compile(r"success\s+rate\s+of\s+(?:approximately\s+|about\s+|around\s+)?(\d{1,3}(?:\.\d+)?)\s*%", re.I),
    re.compile(r"profitable\s+(?:on\s+)?(\d{1,3}(?:\.\d+)?)\s*%\s+of\s+(?:the\s+)?trades", re.I),
]


def extract_claimed_win_rate(raw_text):
    """Returns (win_rate_pct: float|None, source_sentence: str|None) for the
    FIRST plausible win-rate claim found in the document. None, None if the
    text makes no such claim -- never invents a number that isn't there."""
    text = raw_text or ""
    for pattern in _WIN_RATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        pct = float(m.group(1))
        if not (0 < pct <= 100):
            continue
        start = text.rfind(".", 0, m.start()) + 1
        end_dot = text.find(".", m.end())
        end = end_dot + 1 if end_dot != -1 else len(text)
        sentence = text[start:end].strip()
        return pct, (sentence or m.group(0))
    return None, None
