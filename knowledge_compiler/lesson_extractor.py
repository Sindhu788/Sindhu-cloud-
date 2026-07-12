"""Lesson Extractor -- pulls Concept / Rule / Importance / Warnings / Tips /
Psychology / Risk Advice / Examples out of the educational sections of a
compiled document, one candidate Lesson per qualifying bullet/sentence.

Each candidate is handed to the EXISTING knowledge_engine.lesson.new_lesson()
factory unchanged, so condition parsing, rule-type detection, and direction
detection are exactly the same as a lesson typed in by hand -- this module
only decides WHICH sentences are lesson-worthy and what title/category/tags
they get, it never reimplements condition extraction itself.

Sections with no recognizable trading content ("Ignore unrelated narrative")
never produce a lesson.
"""

import re

from knowledge_compiler import dictionary
from knowledge_compiler import sections as sections_mod

_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")

_IMPORTANCE_WORDS = ["important", "critical", "always", "never", "must", "essential", "key rule", "crucial"]
_MISTAKE_WORDS = ["mistake", "don't", "do not", "avoid", "shouldn't", "should not"]

_KIND_TO_CATEGORY_FALLBACK = {
    "mistake": "Other", "strength": "Other", "weakness": "Other",
    "psychology": "Psychology", "risk_advice": "Risk Management",
    "tip": "Other", "example": "Other", "rule": "Other",
}

# Sections that count as explicitly lesson-shaped even if a line doesn't hit
# the dictionary -- e.g. "Wait for the daily candle to close" under a
# Checklist header is a real lesson even with no jargon. SUMMARY/BODY need a
# dictionary hit before they count, so plain narrative is skipped.
_EXPLICIT_LESSON_KINDS = {
    sections_mod.COMMON_MISTAKES, sections_mod.WEAKNESSES, sections_mod.STRENGTHS,
    sections_mod.PSYCHOLOGY, sections_mod.CHECKLIST, sections_mod.RISK, sections_mod.PERFORMANCE,
}


def _split_candidates(section_text):
    lines = [ln.strip() for ln in section_text.splitlines() if ln.strip()]
    candidates = []
    for line in lines:
        m = _BULLET_RE.match(line)
        candidates.append(m.group(1).strip() if m else line)
    # A section with no bullets/newlines but a long paragraph: split on
    # sentence-ending punctuation so one dense paragraph still yields
    # separate, independent lesson candidates rather than one giant blob.
    if len(candidates) <= 1 and candidates and len(candidates[0]) > 160:
        candidates = [s.strip() for s in re.split(r"(?<=[.!?])\s+", candidates[0]) if s.strip()]
    return candidates


def _find_tags(line_lower):
    tags = []
    for entry in dictionary.all_entries():
        for alias in entry.aliases:
            if dictionary.alias_in_text(alias, line_lower):
                if entry.canonical not in tags:
                    tags.append(entry.canonical)
                break
    return tags


def _classify_kind(section_kind, line_lower, tags):
    if section_kind == sections_mod.COMMON_MISTAKES or any(w in line_lower for w in _MISTAKE_WORDS):
        return "mistake"
    if section_kind == sections_mod.STRENGTHS:
        return "strength"
    if section_kind == sections_mod.WEAKNESSES:
        return "weakness"
    if section_kind == sections_mod.PSYCHOLOGY or "psychology" in [dictionary.lookup(t).category if dictionary.lookup(t) else "" for t in tags]:
        return "psychology"
    if section_kind == sections_mod.RISK or "risk" in [dictionary.lookup(t).category if dictionary.lookup(t) else "" for t in tags]:
        return "risk_advice"
    if section_kind == sections_mod.CHECKLIST:
        return "tip"
    if section_kind == sections_mod.PERFORMANCE:
        return "example"
    return "rule"


def _title_for(line):
    words = line.strip().split()
    title = " ".join(words[:9])
    if len(words) > 9:
        title += "..."
    return title[:1].upper() + title[1:] if title else "Untitled Lesson"


def extract_lessons(text, detected_sections=None):
    """Returns a list of candidate lesson dicts:
    {title, category, description, tags, kind, importance, source_section}
    Ready to pass straight into knowledge_engine.lesson.new_lesson(**...)
    after mapping field names (done by the compiler orchestrator)."""
    detected_sections = (
        detected_sections if detected_sections is not None else sections_mod.detect_sections(text)
    )
    relevant = sections_mod.sections_for_lessons(detected_sections)
    results = []
    seen_descriptions = set()

    for section in relevant:
        for candidate in _split_candidates(section.text):
            if len(candidate.split()) < 4:
                continue
            line_lower = candidate.lower()
            tags = _find_tags(line_lower)

            explicit = section.kind in _EXPLICIT_LESSON_KINDS
            if not explicit and not tags:
                continue  # unrelated narrative -- ignored, per spec

            if candidate in seen_descriptions:
                continue
            seen_descriptions.add(candidate)

            kind = _classify_kind(section.kind, line_lower, tags)
            category = dictionary.lesson_category_for(tags[0]) if tags else None
            if not category:
                category = _KIND_TO_CATEGORY_FALLBACK.get(kind, "Other")
            importance = any(w in line_lower for w in _IMPORTANCE_WORDS)

            results.append({
                "title": _title_for(candidate),
                "category": category,
                "description": candidate,
                "tags": tags,
                "kind": kind,
                "importance": importance,
                "source_section": section.heading or section.kind,
            })

    return results
