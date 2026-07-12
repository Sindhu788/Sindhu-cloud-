"""The ONE internal standard structure every supported input document is
converted into, regardless of source style (short strategy, long strategy,
YouTube transcript, NotebookLM/ChatGPT/Claude report, book notes, journal,
mixed strategy+lesson doc, ...). Everything downstream (dashboard preview,
storage, backtesting handoff) reads this shape only.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

READY_FOR_BACKTEST = "READY_FOR_BACKTEST"
NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"

_SOURCE_HINTS = {
    "youtube_transcript": [r"\d{1,2}:\d{2}(:\d{2})?\s", r"\[music\]", r"transcript"],
    "notebooklm": [r"notebooklm"],
    "chatgpt": [r"chatgpt", r"as an ai language model"],
    "claude": [r"\bclaude\b"],
    "pdf_text": [r"\x0c"],  # form-feed page breaks are the usual PDF->text artifact
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def detect_source_type(text, hint=None):
    """Best-effort, deterministic guess at where the pasted text came from --
    informational only, never blocks compilation. An explicit `hint` from
    the CEO (dropdown/param) always wins."""
    if hint:
        return hint
    lower = (text or "").lower()
    for source, patterns in _SOURCE_HINTS.items():
        for pat in patterns:
            if re.search(pat, lower):
                return source
    return "unknown"


@dataclass
class CompiledStrategyResult:
    config: object                  # StrategyConfig
    status: str                     # READY_FOR_BACKTEST | NEEDS_CLARIFICATION
    clarification_notes: list = field(default_factory=list)
    resolved_defaults: list = field(default_factory=list)   # what was auto-filled, for transparency
    dna: str = ""
    saved_strategy_id: str = None

    def to_dict(self):
        d = self.config.to_dict()
        return {
            "config": d, "status": self.status,
            "clarification_notes": self.clarification_notes,
            "resolved_defaults": self.resolved_defaults,
            "dna": self.dna, "saved_strategy_id": self.saved_strategy_id,
        }


@dataclass
class CompiledLessonResult:
    lesson: object                  # Lesson
    dna: str = ""
    kind: str = "rule"
    source_section: str = ""
    saved: bool = False

    def to_dict(self):
        d = self.lesson.to_storage_dict()
        return {"lesson": d, "dna": self.dna, "kind": self.kind, "source_section": self.source_section, "saved": self.saved}


@dataclass
class CompiledDocument:
    id: str
    title: str
    source_type: str
    doc_type: str
    classification_confidence: float
    status: str
    created_at: str = field(default_factory=_now_iso)
    raw_text: str = ""
    sections: list = field(default_factory=list)         # list[Section.to_dict()]
    strategies: list = field(default_factory=list)         # list[CompiledStrategyResult]
    lessons: list = field(default_factory=list)             # list[CompiledLessonResult]
    concepts_used: list = field(default_factory=list)
    unresolved: list = field(default_factory=list)
    clarification_notes: list = field(default_factory=list)
    duplicate_of: list = field(default_factory=list)         # ids of near-identical prior documents/strategies
    conflicts: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    ai_assisted: bool = False
    ai_provider: str = None
    # AI Knowledge Learning Engine (v6): hidden/inferred rules the AI surfaced
    # during deep understanding, each as {"rule", "confidence", "reason",
    # "evidence"} -- purely informational metadata alongside the strategy the
    # deterministic parser already extracted; never affects parsing itself.
    hidden_rules: list = field(default_factory=list)
    psychology_notes: list = field(default_factory=list)
    deep_knowledge: dict = None   # raw AI structured payload, for audit/transparency only

    def to_dict(self):
        return {
            "id": self.id, "title": self.title, "source_type": self.source_type,
            "doc_type": self.doc_type, "classification_confidence": round(self.classification_confidence, 2),
            "status": self.status, "created_at": self.created_at,
            "sections": self.sections,
            "strategies": [s.to_dict() for s in self.strategies],
            "lessons": [l.to_dict() for l in self.lessons],
            "concepts_used": self.concepts_used, "unresolved": self.unresolved,
            "clarification_notes": self.clarification_notes,
            "duplicate_of": self.duplicate_of, "conflicts": self.conflicts,
            "tags": self.tags,
            "ai_assisted": self.ai_assisted, "ai_provider": self.ai_provider,
            "hidden_rules": self.hidden_rules, "psychology_notes": self.psychology_notes,
            "deep_knowledge": self.deep_knowledge,
        }
