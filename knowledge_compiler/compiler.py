"""Orchestrator -- two entry points, sharing one save/dedup/versioning path.

compile_document() is the original text-based pipeline (classify -> detect
sections -> rule_extractor/lesson_extractor -> validate/resolve -> save).
It is used for the CEO's manual paste-a-document workflow, and is the
Offline Mode fallback for the AI Knowledge Learning Engine (v7) when AI is
disabled or unavailable.

compile_from_ai_extraction() is the AI-Native Structured Extraction entry
point (v7): it takes an already-built StrategyConfig/list[Lesson] (built by
ai_integration.strategy_builder directly from the AI's structured output)
and saves them through the exact same dedup/versioning/storage logic --
but never calls rule_extractor.extract_strategy() or
lesson_extractor.extract_lessons(). Per the CEO's explicit v7 directive,
the old text-based extraction path is reserved entirely for
compile_document() / Offline Mode.
"""

import uuid
from datetime import datetime, timezone

from backtest_engine import strategy_library
from knowledge_engine import lesson as lesson_mod
from data_engine import storage

from knowledge_compiler import classifier, compiler_validator, dictionary, quality, rule_extractor
from knowledge_compiler import sections as sections_mod
from knowledge_compiler.lesson_extractor import extract_lessons
from knowledge_compiler.normalizer import (
    CompiledDocument, CompiledLessonResult, CompiledStrategyResult,
    NEEDS_CLARIFICATION, READY_FOR_BACKTEST, detect_source_type,
)

AI_CONFIDENCE_ACCEPT_THRESHOLD = 60.0  # v8: CEO spec -- only ask clarification below 60% AI confidence


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _concepts_in_text(text):
    """All dictionary terms actually mentioned in the raw text, across
    every category -- used for tagging and the Concepts usage tracker.
    Independent of extraction method (AI or old parser): this only tags
    which BUILT-IN dictionary words appear in the source text for search/
    stats purposes, it never extracts strategy rules."""
    text_lower = (text or "").lower()
    found = []
    for entry in dictionary.all_entries():
        if any(dictionary.alias_in_text(alias, text_lower) for alias in entry.aliases):
            if entry.canonical not in found:
                found.append(entry.canonical)
    return found


def _touch_concepts(concepts, now):
    for canonical in concepts:
        entry = dictionary.lookup(canonical)
        storage.touch_knowledge_concept(canonical, entry.category if entry else "unknown", entry.aliases if entry else [], now)


def _existing_lesson_dna_map():
    dna_map = {}
    for stored in storage.list_lessons():
        try:
            existing = lesson_mod.from_storage_dict(stored)
            dna_map[quality.lesson_dna(existing)] = existing.id
        except Exception:
            continue
    return dna_map


def _finalize_and_save_strategy(config, doc_id, now, force_backtest_ready=False, hidden_rules=None, confidence_pct=None):
    """Shared by both pipelines: dedup/merge/conflict-check an already-built
    StrategyConfig, resolve safe defaults, and save with the same duplicate/
    version-by-name logic either path uses. `force_backtest_ready` is only
    ever passed True by the AI-Native Structured Extraction path (v7), when
    the AI's own confidence was >= AI_CONFIDENCE_ACCEPT_THRESHOLD -- the old
    text-parser path never sets it, so its exact existing behavior
    (including genuinely blocking on an unresolved strategy) is unchanged.

    `hidden_rules`/`confidence_pct`: only ever populated by the AI-Native
    path (the AI's own per-field {field,confidence,reason,evidence} reasoning
    -- see ai_integration/schema.py). Persisted onto the saved strategy's own
    record (Part 1, clarification flow) so the Strategies page can show
    exactly why a strategy needs clarification without having to trace back
    through compiled_documents, and cleared the moment the strategy
    re-validates as ready."""
    quality.dedupe_rules(config)
    config.concepts_used = quality.merge_concepts(config.concepts_used)
    conflicts = quality.detect_conflicts(config)

    config, status, clarification_notes, resolved_defaults = compiler_validator.resolve_and_validate(config)
    if force_backtest_ready and status == NEEDS_CLARIFICATION:
        config, status, clarification_notes, resolved_defaults = compiler_validator.force_ready(
            config, clarification_notes, resolved_defaults
        )

    dna = quality.strategy_dna(config)
    dup_id = quality.find_duplicate_strategy(dna, strategy_library.list_all, strategy_library.load)

    saved_id = None
    if dup_id:
        clarification_notes = clarification_notes + [
            f"Identical strategy already exists in the Knowledge Library (id {dup_id}) -- not saved again as a duplicate."
        ]
    else:
        tags = quality.searchable_tags("strategy", config.concepts_used, config.timeframes)
        # Same-named-but-changed strategy: update it as a new version rather
        # than silently creating a second record under the same name -- the
        # same rule the manual Strategies-page save endpoint already
        # follows (Phase 6), applied to both import paths identically.
        existing_id = strategy_library.find_by_name(config.name)
        if existing_id:
            strategy_library.save_version(existing_id, config)
            saved_id = existing_id
            clarification_notes = clarification_notes + [
                f"Updated existing strategy '{config.name}' (id {existing_id}) as a new version."
            ]
        else:
            saved_id = strategy_library.create(config, tags=tags)
        storage.save_knowledge_relationship("compiled_document", doc_id, "strategy", saved_id, "produced", now)
        for concept in config.concepts_used:
            storage.save_knowledge_relationship("strategy", saved_id, "concept", concept, "uses", now)

    all_notes = clarification_notes + conflicts
    if saved_id:
        if status == NEEDS_CLARIFICATION:
            strategy_library.set_clarification(saved_id, {
                "notes": all_notes, "hidden_rules": hidden_rules or [],
                "confidence_pct": confidence_pct, "updated_at": now,
            })
        else:
            strategy_library.set_clarification(saved_id, None)

    return CompiledStrategyResult(
        config=config, status=status, clarification_notes=all_notes,
        resolved_defaults=resolved_defaults, dna=dna, saved_strategy_id=saved_id or dup_id,
    )


def _save_lesson_objects(lesson_entries, doc_id, now):
    """Shared by both pipelines. lesson_entries: list of
    {"lesson": Lesson, "kind": str, "source_section": str}. Both the old
    text-extractor and the AI-Native path (v7) build a real Lesson object
    first (via knowledge_engine.lesson.new_lesson() or
    ai_integration.strategy_builder.build_lesson() respectively) -- this is
    the one shared dedup/save/relationship-tracking step."""
    results = []
    seen_dna_this_doc = set()
    existing_dna_map = _existing_lesson_dna_map()

    for entry in lesson_entries:
        lesson_obj = entry["lesson"]
        if not lesson_obj.is_enforceable():
            lesson_obj.status = "draft"

        dna = quality.lesson_dna(lesson_obj)
        saved = False
        existing_id = existing_dna_map.get(dna)
        if dna in seen_dna_this_doc:
            pass  # duplicate bullet within the same document -- reported, not re-saved
        elif existing_id:
            pass  # identical lesson already in the Knowledge Library
        else:
            storage.save_lesson(lesson_obj.to_storage_dict())
            storage.save_knowledge_relationship("compiled_document", doc_id, "lesson", lesson_obj.id, "produced", now)
            for tag in lesson_obj.tags:
                storage.save_knowledge_relationship("lesson", lesson_obj.id, "concept", tag, "uses", now)
            saved = True
            seen_dna_this_doc.add(dna)

        results.append(CompiledLessonResult(
            lesson=lesson_obj, dna=dna, kind=entry.get("kind", "rule"),
            source_section=entry.get("source_section", ""), saved=saved,
        ))
    return results


def _compile_strategy(text, title, detected_sections, doc_id, now):
    """Old text-based path only: extracts via rule_extractor (which itself
    routes to backtest_engine.strategy_parser) then saves via the shared
    helper above."""
    config = rule_extractor.extract_strategy(text, name=title or "Unnamed Strategy", detected_sections=detected_sections)
    return _finalize_and_save_strategy(config, doc_id, now, force_backtest_ready=False)


def _compile_lessons(text, detected_sections, doc_id, now):
    """Old text-based path only: extracts candidate bullets via
    lesson_extractor, builds each into a real Lesson via
    knowledge_engine.lesson.new_lesson() (which itself routes description
    text through backtest_engine.strategy_parser.parse_conditions()), then
    saves via the shared helper above."""
    candidates = extract_lessons(text, detected_sections=detected_sections)
    entries = []
    for c in candidates:
        lesson_obj = lesson_mod.new_lesson(
            title=c["title"], category=c["category"], description=c["description"],
            priority="Medium", notes=f"Auto-extracted by Knowledge Compiler ({c['kind']}) from section '{c['source_section']}'.",
            tags=c["tags"], apply_backtesting=True, apply_paper_trading=True, apply_evolution=True,
        )
        entries.append({"lesson": lesson_obj, "kind": c["kind"], "source_section": c["source_section"]})
    return _save_lesson_objects(entries, doc_id, now)


def compile_document(
    raw_text, title=None, source_hint=None, ai_assisted=False, ai_provider=None,
    hidden_rules=None, psychology_notes=None, deep_knowledge=None, content_type=None,
):
    """The text-based entry point: classify -> detect sections -> extract ->
    validate/resolve -> quality-check -> auto-save -> return a CompiledDocument.
    Never raises on malformed/ambiguous input -- everything unresolved is
    surfaced in the result instead.

    This is used directly for the CEO's manual paste-a-document workflow,
    and is the AI Knowledge Learning Engine's Offline Mode fallback -- the
    ONLY path that ever calls rule_extractor/lesson_extractor/
    strategy_parser. When AI succeeds, ai_integration.importer routes to
    compile_from_ai_extraction() below instead.

    ai_assisted/ai_provider/hidden_rules/psychology_notes/deep_knowledge:
    purely provenance -- when this function is still called with AI-cleaned
    text from an older flow, these are recorded alongside the document.
    Every extraction/validation/save step below is completely unaffected by
    any of them."""
    if not raw_text or not raw_text.strip():
        raise ValueError("No text provided to compile.")

    doc_id = uuid.uuid4().hex[:12]
    now = _now_iso()
    detected_title, working_text = sections_mod.extract_title(raw_text)
    title = title or detected_title or "Untitled Document"

    classification = classifier.classify_document(working_text)
    detected_sections = sections_mod.detect_sections(working_text)
    source_type = detect_source_type(raw_text, source_hint)
    concepts_found = _concepts_in_text(working_text)
    _touch_concepts(concepts_found, now)

    # Part 2 (explicit type selector): "strategy"/"lesson" override the
    # classifier's own guess outright -- that guess is a real source of
    # strategies coming back misclassified/low-quality. "mixed" (the
    # selector's own default) and unspecified (None) both leave the
    # classifier's free judgment completely unchanged, exactly matching
    # pre-Part-2 behavior -- "Mixed" means "still figure it out yourself",
    # not "force both".
    if content_type == "lesson":
        should_extract_strategy = False
    elif content_type == "strategy":
        should_extract_strategy = True
    else:
        should_extract_strategy = classification.doc_type in (classifier.DOC_STRATEGY, classifier.DOC_MIXED)

    strategies = []
    if should_extract_strategy:
        strategies.append(_compile_strategy(working_text, title, detected_sections, doc_id, now))

    lessons = _compile_lessons(working_text, detected_sections, doc_id, now)

    unresolved = []
    for s in strategies:
        unresolved.extend(s.clarification_notes)

    overall_status = READY_FOR_BACKTEST
    if any(s.status == NEEDS_CLARIFICATION for s in strategies):
        overall_status = NEEDS_CLARIFICATION
    elif not strategies:
        # Nothing executable was extracted -- not a backtest-readiness
        # question at all for a pure Lesson/Psychology/Risk/Indicator/
        # Market-Structure document, so it's trivially "ready" (there's
        # nothing pending clarification).
        overall_status = READY_FOR_BACKTEST

    tags = quality.searchable_tags(classification.doc_type, concepts_found)

    doc = CompiledDocument(
        id=doc_id, title=title, source_type=source_type, doc_type=classification.doc_type,
        classification_confidence=classification.confidence, status=overall_status,
        created_at=now, raw_text=raw_text,
        sections=[s.to_dict() for s in detected_sections],
        strategies=strategies, lessons=lessons, concepts_used=concepts_found,
        unresolved=unresolved, clarification_notes=unresolved, tags=tags,
        ai_assisted=ai_assisted, ai_provider=ai_provider,
        hidden_rules=hidden_rules or [], psychology_notes=psychology_notes or [], deep_knowledge=deep_knowledge,
    )

    # Part 2.1 (auto-trigger backtest on import) -- the Knowledge Compiler
    # page's manual "Compile" flow doesn't route through
    # ai_integration.importer.import_document() at all (see that module's
    # own _maybe_trigger_pipeline for the AI Center / Import Queue side),
    # so this is the matching hook for the Knowledge Compiler side. Same
    # "must be READY_FOR_BACKTEST and actually saved" gate, same
    # never-let-a-pipeline-failure-break-the-import guarantee.
    for s in strategies:
        if s.saved_strategy_id and s.status == READY_FOR_BACKTEST:
            try:
                from automation_pipeline.pipeline import trigger_pipeline_for_strategy
                trigger_pipeline_for_strategy(s.saved_strategy_id, s.config.name)
            except Exception as exc:
                from data_engine.logging_setup import log as file_log
                file_log(f"[automation-pipeline] Failed to auto-trigger for strategy {s.saved_strategy_id}: {exc!r}")

    storage.save_compiled_document({
        "id": doc.id, "title": doc.title, "source_type": doc.source_type, "doc_type": doc.doc_type,
        "classification_confidence": doc.classification_confidence, "status": doc.status,
        "raw_text": doc.raw_text, "sections": doc.sections,
        "strategy_ids": [s.saved_strategy_id for s in strategies if s.saved_strategy_id],
        "lesson_ids": [l.lesson.id for l in lessons if l.saved],
        "concepts": doc.concepts_used, "unresolved": doc.unresolved,
        "clarification_notes": doc.clarification_notes, "tags": doc.tags, "created_at": doc.created_at,
        "ai_assisted": ai_assisted, "ai_provider": ai_provider,
        "hidden_rules": doc.hidden_rules, "psychology_notes": doc.psychology_notes, "deep_knowledge": doc.deep_knowledge,
    })

    return doc


def compile_from_ai_extraction(
    raw_text, title, source_hint, ai_provider, confidence_pct,
    strategy_config, lesson_objects, inferred_fields, psychology_notes, missing_rules, deep_knowledge,
):
    """AI-Native Structured Extraction entry point (v7, AI Knowledge
    Learning Engine). `strategy_config` is either an already-built
    StrategyConfig (from ai_integration.strategy_builder.build_strategy_config(),
    or None if the document had no executable strategy). `lesson_objects` is
    a list of already-built Lesson objects (from
    ai_integration.strategy_builder.build_lesson()). Neither is extracted or
    re-parsed here -- this function only dedups/validates/saves, through the
    exact same shared helpers compile_document() uses, and NEVER calls
    rule_extractor.extract_strategy() or lesson_extractor.extract_lessons().

    When confidence_pct >= AI_CONFIDENCE_ACCEPT_THRESHOLD, the AI's own
    understanding is accepted as the source of truth: status is always
    READY_FOR_BACKTEST (no clarification gate), and a strategy that's still
    missing its one safety-critical field (stop-loss) after normal
    defaulting gets one last, clearly-logged automatic default instead of
    blocking -- this is what "every imported strategy must automatically
    become Backtesting Ready, no manual editing" means in code. Below that
    threshold, status reflects genuine unresolved issues (AI's own
    missing_rules plus any real validator errors), same spirit as the old
    pipeline's clarification notes."""
    if not raw_text or not raw_text.strip():
        raise ValueError("No text provided to compile.")

    doc_id = uuid.uuid4().hex[:12]
    now = _now_iso()
    detected_title, _ = sections_mod.extract_title(raw_text)
    title = title or detected_title or (strategy_config.name if strategy_config else None) or "Untitled Document"
    source_type = detect_source_type(raw_text, source_hint)

    strategies = []
    if strategy_config is not None:
        strategies.append(_finalize_and_save_strategy(
            strategy_config, doc_id, now,
            force_backtest_ready=(confidence_pct >= AI_CONFIDENCE_ACCEPT_THRESHOLD),
            hidden_rules=inferred_fields, confidence_pct=confidence_pct,
        ))

    lesson_entries = [{"lesson": lesson_obj, "kind": "ai_extracted", "source_section": "AI"} for lesson_obj in lesson_objects]
    lessons = _save_lesson_objects(lesson_entries, doc_id, now)

    unresolved = []
    for s in strategies:
        unresolved.extend(s.clarification_notes)
    unresolved.extend(f"AI-reported gap: {m}" for m in missing_rules)

    if strategy_config is None:
        # Nothing executable was extracted -- not a backtest-readiness
        # question at all for a pure Lesson/Psychology/Risk/Market-Structure
        # document, so it's trivially ready (same reasoning compile_document()
        # already applies to a document with no strategy).
        overall_status = READY_FOR_BACKTEST
    elif confidence_pct >= AI_CONFIDENCE_ACCEPT_THRESHOLD:
        overall_status = READY_FOR_BACKTEST
    else:
        # CEO spec, literal: "Only request clarification if confidence is
        # below 60%" -- confidence alone gates this, independent of whether
        # the extracted structure happens to already validate cleanly on
        # its own merits (a low-confidence AI read is still worth a second
        # look even if it looks complete).
        overall_status = NEEDS_CLARIFICATION

    concepts_found = list(strategy_config.concepts_used) if strategy_config is not None else []
    built_in_concepts = _concepts_in_text(raw_text)
    _touch_concepts(built_in_concepts, now)
    for canonical in built_in_concepts:
        if canonical not in concepts_found:
            concepts_found.append(canonical)

    doc_type = (
        "MIXED" if strategies and lessons else
        "STRATEGY" if strategies else
        "LESSON" if lessons else
        "UNKNOWN"
    )
    tags = quality.searchable_tags(doc_type, concepts_found)

    doc = CompiledDocument(
        id=doc_id, title=title, source_type=source_type, doc_type=doc_type,
        classification_confidence=confidence_pct / 100.0, status=overall_status,
        created_at=now, raw_text=raw_text, sections=[],
        strategies=strategies, lessons=lessons, concepts_used=concepts_found,
        unresolved=unresolved, clarification_notes=unresolved, tags=tags,
        ai_assisted=True, ai_provider=ai_provider,
        hidden_rules=inferred_fields, psychology_notes=psychology_notes, deep_knowledge=deep_knowledge,
    )

    storage.save_compiled_document({
        "id": doc.id, "title": doc.title, "source_type": doc.source_type, "doc_type": doc.doc_type,
        "classification_confidence": doc.classification_confidence, "status": doc.status,
        "raw_text": doc.raw_text, "sections": doc.sections,
        "strategy_ids": [s.saved_strategy_id for s in strategies if s.saved_strategy_id],
        "lesson_ids": [l.lesson.id for l in lessons if l.saved],
        "concepts": doc.concepts_used, "unresolved": doc.unresolved,
        "clarification_notes": doc.clarification_notes, "tags": doc.tags, "created_at": doc.created_at,
        "ai_assisted": True, "ai_provider": ai_provider,
        "hidden_rules": doc.hidden_rules, "psychology_notes": doc.psychology_notes, "deep_knowledge": doc.deep_knowledge,
    })

    return doc
