"""Self-Building Dictionary (v6) -- whenever a new trading term is
discovered during import, it is permanently saved to the ai_dictionary_entries
table with a full profile: definition, category, aliases, examples, related
concepts, and usage notes. The static knowledge_compiler.dictionary module is
never modified at runtime; this is a separate, additive, growing dictionary
layered on top of it -- the same relationship compiled_documents/
knowledge_concepts already have to the rest of the Knowledge Compiler.

Two independent discovery paths, so the dictionary keeps growing even with
AI fully disabled:
1. Deterministic, AI-independent: parenthetical acronym/expansion pairs
   already present in the raw text (e.g. "Break of Structure (BOS)"). Only
   ever yields a bare term + definition -- no aliases/examples/category
   beyond a generic default, since there's no AI judgement behind it.
2. AI-assisted: the Deep Understanding pass (ai_integration.deep_understanding)
   returns a `dictionary_terms` list with the full profile already filled
   in by the provider, reading only the CEO's own pasted document -- never
   invented from nothing.
"""

import re
from datetime import datetime, timezone

from data_engine import storage
from knowledge_compiler import dictionary as static_dictionary

_ACRONYM_IN_PARENS_RE = re.compile(r"([A-Za-z][A-Za-z' ]{2,60}?)\s*\(([A-Z]{2,6})\)")
_EXPANSION_IN_PARENS_RE = re.compile(r"\b([A-Z]{2,6})\s*\(([A-Za-z][A-Za-z' ]{2,60}?)\)")
_WORD_RE = re.compile(r"[A-Za-z']+")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _tighten_expansion(phrase, acronym):
    """'Wait for a Smart Money Technique' + 'SMT' -> 'Smart Money Technique'.
    Parenthetical definitions are often preceded by filler words the naive
    regex also swept up; this keeps only the shortest trailing run of words
    whose initials actually spell the acronym (the standard way humans write
    real acronym expansions), so the saved definition is the precise phrase
    rather than a whole leading clause."""
    words = _WORD_RE.findall(phrase)
    target = acronym.lower()
    for start in range(len(words)):
        candidate = words[start:]
        initials = "".join(w[0] for w in candidate).lower()
        if initials == target:
            return " ".join(candidate)
    return phrase.strip()


def _is_known(term):
    key = term.strip().lower()
    if static_dictionary.lookup(key):
        return True
    return storage.get_ai_dictionary_entry(key) is not None


def discover_from_raw_text(text):
    """Deterministic, AI-independent discovery via parenthetical
    acronym/expansion patterns already present in the source text (either
    'Break of Structure (BOS)' or 'BOS (Break of Structure)' order). Returns
    a list of term-profile dicts (bare term + definition only -- category
    defaults to "structure", no aliases/examples/related_concepts since
    there's no AI judgement behind this path) for terms not already known to
    either the static dictionary or a prior self-building discovery."""
    text = text or ""
    found = {}
    for expansion, acronym in _ACRONYM_IN_PARENS_RE.findall(text):
        term = acronym.strip()
        if term and not _is_known(term) and term not in found:
            found[term] = _tighten_expansion(expansion, term)
    for acronym, expansion in _EXPANSION_IN_PARENS_RE.findall(text):
        term = acronym.strip()
        if term and not _is_known(term) and term not in found:
            found[term] = _tighten_expansion(expansion, term)
    return [
        {
            "term": term, "definition": definition, "category": "structure",
            "aliases": [], "examples": [], "related_concepts": [], "usage": "",
        }
        for term, definition in found.items()
    ]


def save_discovered_terms(entries, doc_id):
    """entries: a list of term-profile dicts, each with at least
    term/definition and optionally category/aliases/examples/
    related_concepts/usage (from ai_integration.schema.parse_deep_response's
    "dictionary_terms", or from discover_from_raw_text() above). Insert-or-
    refresh into ai_dictionary_entries, skipping anything already known by
    the time this runs (a term discovered twice in the same batch, or
    already known from a prior import, only needs saving once per batch)."""
    saved = []
    now = _now_iso()
    for entry in entries:
        term = (entry.get("term") or "").strip()
        definition = (entry.get("definition") or "").strip()
        if not term or not definition or _is_known(term):
            continue
        category = entry.get("category") or "structure"
        aliases = entry.get("aliases") or []
        keywords = [
            w for w in {w.strip().lower() for w in re.split(r"[ ,/]+", definition)} if len(w) > 2
        ]
        storage.save_ai_dictionary_entry(
            term.lower(), definition, keywords, category, doc_id, now,
            aliases=aliases, examples=entry.get("examples") or [],
            related_concepts=entry.get("related_concepts") or [], usage_notes=entry.get("usage") or None,
        )
        saved.append({"canonical_name": term.lower(), "definition": definition, "category": category})
    return saved
