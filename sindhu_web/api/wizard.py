"""Strategy Wizard API -- a second, independent way to reach the exact
same StrategyConfig the free-text parser builds, via explicit form input
instead of interpreting prose. See backtest_engine/wizard.py for the pure
builder logic; this module is only the thin HTTP layer around it plus the
one genuinely optional AI call (classify-other)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backtest_engine import wizard, strategy_library as lib
from ai_integration import config as ai_config
from ai_integration.deep_understanding import call_provider_chain_generic

router = APIRouter()


@router.get("/api/wizard/concept-library")
def get_concept_library():
    """The engine's real, current condition vocabulary -- read live from
    validator.py so the Wizard's dropdowns can never drift out of sync
    with what the backtest engine actually computes."""
    return wizard.known_concept_catalog()


class ClassifyRequest(BaseModel):
    raw_text: str


def _parse_classify_response(text, known_concepts):
    answer = text.strip().strip('."\'').lower()
    for concept in known_concepts:
        if answer == concept.lower():
            return concept
    return None  # "NONE" or anything unrecognized -- never guess a close-enough match


@router.post("/api/wizard/classify-other")
def classify_other(req: ClassifyRequest):
    """The ONE optional AI call in the whole Wizard: "does this free-text
    description match an existing concept?" Never blocks the Wizard --
    if no AI provider is configured/enabled/has a key, or every provider
    fails, this returns matched_concept=None and ai_available=False, and
    the caller (the frontend) falls straight through to the manual-review
    path, exactly as if this endpoint had said "no match"."""
    chain = ai_config.provider_fallback_chain()
    catalog = wizard.known_concept_catalog()
    known_concepts = catalog["concepts"] + catalog["indicators"]
    if not chain:
        return {"matched_concept": None, "ai_available": False, "provider": None}

    system_prompt = (
        "A trader described a chart condition in their own words. Your ONLY job is to say "
        "which ONE of these known concept names it most closely matches, or say it matches "
        "none of them. Known concept names: " + ", ".join(known_concepts) + ". "
        "Reply with ONLY the exact matching name from that list (nothing else), or the single "
        "word NONE if nothing is a close match. No explanation, no punctuation."
    )

    def parse_fn(text):
        return _parse_classify_response(text, known_concepts) or "NONE"

    parsed, provider, error = call_provider_chain_generic(
        req.raw_text, chain, system_prompt, "/api/wizard/classify-other", parse_fn,
    )
    if parsed is None or parsed == "NONE":
        return {"matched_concept": None, "ai_available": True, "provider": provider}
    return {"matched_concept": parsed, "ai_available": True, "provider": provider}


class SaveRequest(BaseModel):
    wizard_data: dict
    tags: list = []


@router.post("/api/wizard/save")
def save_wizard_strategy(req: SaveRequest):
    """NEVER REJECT: always saves, even with Manual Review items present --
    those conditions are just excluded from execution (see
    wizard.has_manual_review + the run_backtest guard in backtesting.py)
    until resolved, never from being saved at all."""
    try:
        config, trust_report = wizard.build_strategy_config(req.wizard_data)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # lib.create() runs the Automatic Strategy Safety Check itself (the
    # same choke point every other save path already goes through) and
    # stores safety_status/safety_reasons in the strategy's own metadata
    # -- it never blocks the save, exactly matching NEVER REJECT.
    strategy_id = lib.create(config, tags=(req.tags or []) + ["wizard-built"])
    return {
        "strategy_id": strategy_id,
        "trust_report": trust_report,
        "config": config.to_dict(),
    }
