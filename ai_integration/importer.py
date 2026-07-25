"""AI Knowledge Learning Engine (v7) -- the one orchestrator every import
entry point (paste text, upload PDF/DOCX/TXT, paste a YouTube link, the
Import Queue worker) calls.

Per the CEO's explicit v7 architecture requirement: when AI succeeds, its
structured output is used DIRECTLY as the source of truth -- built into a
real StrategyConfig/Lesson objects by ai_integration.strategy_builder and
saved via knowledge_compiler.compiler.compile_from_ai_extraction(). AI
output is NEVER routed back through the old text-based pipeline
(rule_extractor/strategy_parser/lesson_extractor). That old pipeline
(compile_document()) is reserved ENTIRELY for Offline Mode: AI disabled,
unconfigured, or every provider in the fallback chain failed for the whole
document. Nothing here ever raises -- a totally unusable input, a broken
YouTube link, or an AI response that somehow still fails to save is
reported back, never thrown."""

import hashlib
import re
from datetime import datetime, timezone

from data_engine import storage
from knowledge_compiler.compiler import compile_document, compile_from_ai_extraction

from ai_integration import deep_understanding
from ai_integration import dictionary_builder
from ai_integration import self_correction
from ai_integration import strategy_builder
from ai_integration import youtube_import
from ai_integration.quality_score import compute_knowledge_score

_MISSING_RULE_MARKERS = ("Missing entry rules", "Missing exit rules", "Unclear entry rule", "Unclear exit rule")
_RISK_MARKERS = ("Missing stop loss", "Missing take profit", "Missing risk", "Invalid risk")
_SESSION_MARKERS = ("session",)
_PATTERN_MARKERS = ("indicator/concept",)
_INDICATOR_MARKERS = ("Invalid indicator",)

_WHITESPACE_RE = re.compile(r"\s+")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _content_hash(text):
    """v8: normalized-content fingerprint for the pre-AI dedup cache --
    whitespace/case-insensitive so trivial re-pasting of the same document
    still hits the cache. Deliberately NOT the same as
    knowledge_compiler.quality.strategy_dna (that fingerprints the extracted
    RULES post-hoc for save-time dedup/versioning); this one fingerprints
    the raw INPUT so an identical document can skip calling AI at all."""
    normalized = _WHITESPACE_RE.sub(" ", (text or "").strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _categorize_notes(notes):
    """Buckets the compiler's plain-English clarification/unresolved
    strings (plus the AI's own "missing_rules"/"AI-reported gap" notes)
    into the Import Report categories the spec calls for. Purely a
    string-keyword classifier -- no new parsing logic, no guessing."""
    report = {
        "missing_rules": [], "unknown_indicators": [], "unknown_pattern": [],
        "unknown_session": [], "unknown_risk_rule": [], "other": [],
    }
    for note in notes:
        lower = note.lower()
        if any(m.lower() in lower for m in _SESSION_MARKERS) and "session" in lower:
            report["unknown_session"].append(note)
        elif any(m.lower() in lower for m in _PATTERN_MARKERS):
            report["unknown_pattern"].append(note)
        elif any(m.lower() in lower for m in _INDICATOR_MARKERS):
            report["unknown_indicators"].append(note)
        elif any(m.lower() in lower for m in _RISK_MARKERS):
            report["unknown_risk_rule"].append(note)
        elif any(m.lower() in lower for m in _MISSING_RULE_MARKERS):
            report["missing_rules"].append(note)
        else:
            report["other"].append(note)
    return report


def _maybe_trigger_pipeline(doc_dict):
    """Part 2.1 (auto-trigger backtest on import): the single choke point
    both callers below (_offline_result and the AI-native success path)
    share -- so every import_document() entry point (text paste, file
    upload, YouTube, and the Import Queue worker, which all call
    import_document() directly) triggers the automation pipeline
    identically, without needing a separate hook at each API route. Never
    lets a pipeline-start failure break the import itself."""
    if not doc_dict:
        return
    for s in doc_dict.get("strategies", []):
        strategy_id = s.get("saved_strategy_id")
        if strategy_id and s.get("status") == "READY_FOR_BACKTEST":
            try:
                from automation_pipeline.pipeline import trigger_pipeline_for_strategy
                trigger_pipeline_for_strategy(strategy_id, s.get("config", {}).get("name"))
            except Exception as exc:
                from data_engine.logging_setup import log as file_log
                file_log(f"[automation-pipeline] Failed to auto-trigger for strategy {strategy_id}: {exc!r}")


def _empty_input_result(error_text):
    return {
        "document": None, "ai_assisted": False, "ai_provider": None,
        "ai_error": None, "served_from_cache": False, "import_report": _categorize_notes([error_text]),
        "quality_score": None, "new_dictionary_entries": [], "hidden_rules": [], "psychology_notes": [],
        "error": error_text,
    }


def _offline_result(raw_text, title, source_hint, ai_error, content_type=None):
    """Pure rule-based pipeline -- the ONLY path that ever calls
    compile_document()'s text-based extraction (rule_extractor/
    strategy_parser/lesson_extractor). Used when AI is disabled,
    unconfigured, every provider failed on the whole document, or (rarely)
    an AI-extracted structure somehow still failed to save. Never raises."""
    dictionary_entries = dictionary_builder.discover_from_raw_text(raw_text)
    try:
        doc = compile_document(raw_text, title=title, source_hint=source_hint, content_type=content_type)
    except Exception as exc:
        return {
            "document": None, "ai_assisted": False, "ai_provider": None,
            "ai_error": ai_error, "served_from_cache": False, "import_report": _categorize_notes([]),
            "quality_score": None, "new_dictionary_entries": [], "hidden_rules": [], "psychology_notes": [],
            "error": str(exc),
        }

    notes = list(doc.unresolved) + [n for n in doc.clarification_notes if n not in doc.unresolved]
    doc_dict = doc.to_dict()
    new_dictionary_entries = dictionary_builder.save_discovered_terms(dictionary_entries, doc.id)
    _maybe_trigger_pipeline(doc_dict)
    return {
        "document": doc_dict,
        "ai_assisted": False,
        "ai_provider": None,
        "ai_error": ai_error,
        "served_from_cache": False,
        "import_report": _categorize_notes(notes),
        "quality_score": compute_knowledge_score(doc_dict),
        "new_dictionary_entries": new_dictionary_entries,
        "hidden_rules": [],
        "psychology_notes": [],
        "error": None,
    }


def import_document(raw_text, title=None, source_hint=None, use_ai=True, input_kind="text", content_type=None):
    """The single entry point for every supported input.

    input_kind: "text" (default -- pasted strategy/lesson/notes, or text
    already extracted from a PDF/DOCX upload) or "youtube" (raw_text is
    treated as the video URL and its transcript is fetched/cleaned first).

    content_type (Part 2): "strategy" | "lesson" | "mixed"/None -- an
    explicit up-front declaration of what kind of content this is, instead
    of leaving the classifier/AI to guess purely from the text (a real
    source of strategies coming back low-confidence/misclassified). "mixed"
    and None behave identically to the pre-Part-2 default (free guess);
    "strategy"/"lesson" steer both the AI prompt (schema.py) and, on the
    Offline Mode path, the old classifier-driven compile_document() call.
    "lesson" is additionally enforced in code below (not just prompted) --
    strategy_config is forced to None even if the AI ignored the
    instruction, since prompt-following alone isn't reliable enough for a
    hard guarantee.

    Returns a dict: {"document": CompiledDocument.to_dict() or None,
    "ai_assisted": bool, "ai_provider": str|None, "ai_error": str|None,
    "import_report": {...}, "quality_score": {...}|None,
    "new_dictionary_entries": [...], "hidden_rules": [...] (now
    {field,confidence,reason,evidence} entries -- which specific strategy
    fields the AI inferred rather than read explicitly),
    "psychology_notes": [...], "error": str|None}."""
    resolved_source_hint = source_hint

    if input_kind == "youtube":
        text, video_id, yt_error = youtube_import.import_from_url(raw_text)
        if not text:
            return _empty_input_result(yt_error or "Could not import YouTube video.")
        raw_text = text
        title = title or f"YouTube Import ({video_id})"
        resolved_source_hint = "youtube_transcript"

    if not raw_text or not raw_text.strip():
        return _empty_input_result("Missing entry rules. No text was provided.")

    # v8: pre-AI dedup cache -- "if a strategy/document already exists,
    # never call AI again for it." Content-hash lookup happens BEFORE any
    # provider is touched; on a hit, the cached structured result is reused
    # exactly as if AI had just answered, so the rest of the pipeline
    # (build -> save -> dedupe/version) is completely unchanged.
    served_from_cache = False
    content_hash = _content_hash(raw_text)
    ai_result, provider_name, ai_error = None, None, None
    if use_ai:
        cached_result, cached_provider = storage.get_ai_import_cache(content_hash)
        if cached_result is not None:
            ai_result, provider_name, served_from_cache = cached_result, cached_provider, True

    if not served_from_cache:
        understanding = deep_understanding.understand_document_structured(
            raw_text, use_ai, source_hint=resolved_source_hint, content_type=content_type,
        )
        ai_result, provider_name, ai_error = understanding["result"], understanding["provider"], understanding["error"]

    if ai_result is None:
        # AI disabled, unconfigured, or every provider failed on the whole
        # document -- Offline Mode, the only case the old parser ever runs.
        return _offline_result(raw_text, title, resolved_source_hint, ai_error, content_type=content_type)

    # AI-Native Structured Extraction: build real objects directly from the
    # AI's own output (fresh or cached). The old text-parser pipeline is
    # never touched here. content_type == "lesson" is enforced here, not
    # just prompted -- a hard guarantee, not a suggestion the AI might miss.
    confidence_pct = ai_result["confidence"]
    strategy_config = (
        strategy_builder.build_strategy_config(ai_result["strategy"], title, raw_text)
        if ai_result["strategy"] and content_type != "lesson" else None
    )

    # Self-Correcting Import Pipeline. The AI has already been asked to
    # self-verify inside the extraction call above (Level 1, preventive --
    # see schema.py's SELF-VERIFICATION block), but prompt-following alone
    # is not a guarantee, so every built strategy is independently
    # re-checked here and repaired: deterministic structural fixes first
    # (Level 1, zero AI calls), then at most ONE small targeted follow-up
    # call scoped to whatever is left (Level 2), and only if BOTH fail is
    # the user asked anything at all (Level 3, plain language). The user
    # has no trading background and cannot resolve a rule conflict
    # themselves, so "detected but not fixed" is never an acceptable
    # outcome here.
    correction = None
    if strategy_config is not None:
        correction = self_correction.self_correct(strategy_config, use_ai=use_ai)
        if correction["level"] == 3 and correction["user_message"]:
            ai_result = dict(ai_result)
            ai_result["missing_rules"] = list(ai_result["missing_rules"]) + [correction["user_message"]]

    lesson_objects = [strategy_builder.build_lesson(l) for l in ai_result["lessons"]]

    # Self-Building Dictionary: the AI's own reported terms, plus the
    # deterministic, AI-independent acronym scan (keeps growing even with
    # AI fully disabled on some future import).
    dictionary_entries = list(ai_result["dictionary_terms"]) + dictionary_builder.discover_from_raw_text(raw_text)

    try:
        doc = compile_from_ai_extraction(
            raw_text, title, resolved_source_hint, provider_name, confidence_pct,
            strategy_config, lesson_objects, ai_result["inferred_fields"], ai_result["psychology_notes"],
            ai_result["missing_rules"], ai_result,
        )
    except Exception as exc:
        # Never trust AI-extracted structure blindly: if saving it somehow
        # fails, fall back once to pure rule-based parsing of the raw text
        # rather than losing the import entirely.
        fallback_error = (f"{ai_error} " if ai_error else "") + f"AI-extracted structure failed to save ({exc}); used rule-based parsing instead."
        return _offline_result(raw_text, title, resolved_source_hint, fallback_error)

    if not served_from_cache:
        # Only cache a FRESH AI answer -- never re-cache a cache hit (would
        # just rewrite the same row), and never cache after a transient
        # failure (that's handled by falling back to Offline Mode above,
        # not by this success path at all).
        storage.save_ai_import_cache(content_hash, ai_result, provider_name, _now_iso())

    notes = list(doc.unresolved) + [n for n in doc.clarification_notes if n not in doc.unresolved]
    doc_dict = doc.to_dict()
    new_dictionary_entries = dictionary_builder.save_discovered_terms(dictionary_entries, doc.id)
    _maybe_trigger_pipeline(doc_dict)
    return {
        "document": doc_dict,
        "ai_assisted": True,
        "ai_provider": provider_name,
        "ai_error": ai_error,
        "served_from_cache": served_from_cache,
        "import_report": _categorize_notes(notes),
        "quality_score": compute_knowledge_score(doc_dict),
        "new_dictionary_entries": new_dictionary_entries,
        "hidden_rules": doc.hidden_rules,
        "psychology_notes": doc.psychology_notes,
        "self_correction": correction,
        "error": None,
    }
