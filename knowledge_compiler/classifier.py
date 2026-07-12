"""Rule-based document classifier -- no AI/ML. Scores a pasted document
against keyword buckets per supported document type and picks the highest
scorer. Every bucket is plain keyword/regex counting, consistent with the
rest of SINDHU's "deterministic, never guess" parsing philosophy.
"""

import re
from dataclasses import dataclass, field

from knowledge_compiler import dictionary as dict_mod

DOC_STRATEGY = "STRATEGY"
DOC_LESSON = "LESSON"
DOC_MIXED = "MIXED"
DOC_PSYCHOLOGY = "PSYCHOLOGY"
DOC_RISK_MANAGEMENT = "RISK_MANAGEMENT"
DOC_INDICATOR_GUIDE = "INDICATOR_GUIDE"
DOC_MARKET_STRUCTURE = "MARKET_STRUCTURE"
DOC_UNKNOWN = "UNKNOWN"

_ENTRY_EXIT_KEYWORDS = [
    "entry rule", "entry rules", "entry:", "entry condition", "entry setup",
    "exit rule", "exit rules", "exit:", "exit condition",
    "buy when", "sell when", "enter when", "enter long", "enter short",
    "go long", "go short", "setup:", "trade setup", "stop loss", "sl:",
    "take profit", "tp:", "risk reward", "risk:reward", "position size",
    "entry timeframe", "confirmation:",
]

_LESSON_KEYWORDS = [
    "lesson", "mistake", "mistakes", "never do", "always remember",
    "tip:", "tips:", "important:", "note:", "remember that", "common mistake",
    "weakness", "weaknesses", "strength", "strengths", "warning:",
    "beginners often", "many traders", "checklist", "rule of thumb",
    "key takeaway", "takeaways",
    # "avoid" alone is deliberately excluded -- it's extremely common in
    # ordinary strategy filter text ("avoid trading during news", "avoid
    # ranging markets") and previously caused clean strategy documents to
    # be misclassified as MIXED with no real lesson content present.
]

_IF_THEN_RE = re.compile(r"\b(if|agar)\b[^.\n]{0,80}\b(then|to)\b", re.IGNORECASE)

_MIN_SIGNAL = 2          # below this, nothing scored meaningfully -> UNKNOWN
_MIXED_RATIO = 0.55       # if the second bucket is within this ratio of the top, it's MIXED


def _count_keywords(text_lower, keywords):
    return sum(text_lower.count(kw) for kw in keywords)


def _count_category(text_lower, category):
    total = 0
    for entry in dict_mod.entries_by_category(category):
        for alias in entry.aliases:
            if dict_mod.alias_in_text(alias, text_lower):
                total += 1
    return total


@dataclass
class DocClassification:
    doc_type: str
    confidence: float
    scores: dict = field(default_factory=dict)

    def to_dict(self):
        return {"doc_type": self.doc_type, "confidence": round(self.confidence, 2), "scores": self.scores}


def classify_document(text):
    """Deterministic keyword-bucket scoring. Never returns a confidence of
    1.0 -- always leaves room for CEO judgement, and returns UNKNOWN rather
    than guessing when nothing scores meaningfully."""
    text_lower = (text or "").lower()

    entry_exit_score = _count_keywords(text_lower, _ENTRY_EXIT_KEYWORDS) + len(_IF_THEN_RE.findall(text_lower))
    lesson_score = _count_keywords(text_lower, _LESSON_KEYWORDS)
    psychology_score = _count_category(text_lower, dict_mod.CATEGORY_PSYCHOLOGY)
    risk_score = _count_category(text_lower, dict_mod.CATEGORY_RISK)
    indicator_score = _count_category(text_lower, dict_mod.CATEGORY_INDICATOR)
    structure_score = _count_category(text_lower, dict_mod.CATEGORY_STRUCTURE) + _count_category(text_lower, dict_mod.CATEGORY_TREND)

    scores = {
        "strategy_rules": entry_exit_score,
        "lesson": lesson_score,
        "psychology": psychology_score,
        "risk_management": risk_score,
        "indicator_guide": indicator_score,
        "market_structure": structure_score,
    }
    total_signal = sum(scores.values())

    has_rules = entry_exit_score >= _MIN_SIGNAL
    # A lesson signal counts as "educational" on its own; heavy psychology/risk
    # commentary with no rule structure also reads as lesson-shaped content.
    has_lesson = lesson_score >= _MIN_SIGNAL or (
        entry_exit_score < _MIN_SIGNAL and (psychology_score + risk_score) >= _MIN_SIGNAL
    )

    if total_signal < _MIN_SIGNAL:
        return DocClassification(DOC_UNKNOWN, 0.0, scores)

    if has_rules and has_lesson:
        doc_type = DOC_MIXED
        confidence = min(entry_exit_score, lesson_score + psychology_score + risk_score) / total_signal
    elif has_rules:
        doc_type = DOC_STRATEGY
        confidence = entry_exit_score / total_signal
    else:
        # No executable rule structure -- pick the single dominant bucket.
        ranked = sorted(
            [
                (lesson_score, DOC_LESSON),
                (psychology_score, DOC_PSYCHOLOGY),
                (risk_score, DOC_RISK_MANAGEMENT),
                (indicator_score, DOC_INDICATOR_GUIDE),
                (structure_score, DOC_MARKET_STRUCTURE),
            ],
            reverse=True,
        )
        top_score, doc_type = ranked[0]
        if top_score < _MIN_SIGNAL:
            return DocClassification(DOC_UNKNOWN, 0.0, scores)
        second_score = ranked[1][0] if len(ranked) > 1 else 0
        if second_score and second_score / top_score >= _MIXED_RATIO:
            doc_type = DOC_LESSON if doc_type != DOC_LESSON and lesson_score > 0 else doc_type
        confidence = top_score / total_signal

    confidence = max(0.3, min(0.95, confidence))
    return DocClassification(doc_type, confidence, scores)
