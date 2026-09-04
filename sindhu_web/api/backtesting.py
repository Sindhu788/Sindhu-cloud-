import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_engine import storage
from data_engine.control import DownloadControl
from backtest_engine.strategy_parser import parse_strategy_text
from backtest_engine.strategy_config import StrategyConfig
from backtest_engine.validator import validate
from backtest_engine.strategy_safety_check import run_safety_check
from backtest_engine.performance_dashboard import evaluate_strategy_performance
from backtest_engine import strategy_library as lib
from backtest_engine import wizard
from backtest_engine import runner
from backtest_engine import sanity_check
from backtest_engine.reports import generate_report
from backtest_engine import monte_carlo, stress_test, result_plausibility, slippage_sensitivity, duration_tracker
from backtest_engine import what_if_simulator, feature_importance, cross_coin_validation, strategy_variants
from automation_pipeline import optimizer as grid_optimizer
from automation_pipeline import genetic_optimizer
from ai_integration import extraction_lock, multi_pass_extraction, sentence_level_extraction
from knowledge_compiler import quality as kc_quality
from data_engine.resample import get_ohlcv
from sindhu_web.jobs import job_manager
from sindhu_web.api.data import _default_exchange
from sindhu_web import sync, cache


def _now_iso():
    return datetime.now(timezone.utc).isoformat()

router = APIRouter()


class ParseRequest(BaseModel):
    text: str
    name: str = "Unnamed Strategy"


@router.post("/api/backtesting/parse")
def parse_strategy(req: ParseRequest):
    cfg = parse_strategy_text(req.text, name=req.name)
    errors = validate(cfg)
    return {"config": cfg.to_dict(), "errors": errors, "valid": not errors}


class SaveRequest(BaseModel):
    config: Dict[str, Any]
    tags: List[str] = []
    strategy_id: Optional[str] = None


@router.post("/api/backtesting/strategies")
def save_strategy(req: SaveRequest):
    """If strategy_id is given, updates that existing strategy (new
    version) instead of creating a new one -- this is what lets the
    frontend autosave on every edit without piling up duplicate records.
    If no strategy_id is given but a strategy with the SAME NAME already
    exists, that one is updated (a new version) too -- saving a strategy
    under a name that's already in the library must never silently create
    a second, duplicate entry."""
    cfg = StrategyConfig.from_dict(req.config)
    strategy_id = req.strategy_id or lib.find_by_name(cfg.name)
    if strategy_id:
        try:
            lib.save_version(strategy_id, cfg)
            cache.invalidate(_STRATEGIES_CACHE_KEY)
            sync.notify("strategy", "updated", f"Strategy updated: {cfg.name}", id=strategy_id)
            return {"id": strategy_id}
        except FileNotFoundError:
            pass
    strategy_id = lib.create(cfg, tags=req.tags)
    cache.invalidate(_STRATEGIES_CACHE_KEY)
    sync.notify("strategy", "created", f"Strategy added: {cfg.name}", id=strategy_id)
    return {"id": strategy_id}


class SimilarityCheckRequest(BaseModel):
    concepts_used: list[str]
    exclude_strategy_id: Optional[str] = None


@router.post("/api/backtesting/strategies/similarity-check")
def check_strategy_similarity(req: SimilarityCheckRequest):
    """Grand Feature Expansion, Phase 4 Feature 2: called by the frontend
    BEFORE the actual save action (see save_strategy above, left
    completely unmodified) so a warning can be shown and confirmed without
    ever blocking or altering the real save."""
    return {"warnings": lib.find_similarity_warnings(req.concepts_used, exclude_strategy_id=req.exclude_strategy_id)}


def _strategy_last_batch_result(strategy_name, recent_batches, batch_results_cache=None):
    """Lightweight summary straight from each result's already-computed
    metrics_json -- deliberately NOT generate_report(), which also builds
    full rankings/session analysis and writes report.json/.txt to disk on
    every call. That's the right tool for viewing one report, but calling
    it once per strategy just to populate a list view made this endpoint
    scale badly (measured ~800ms per strategy) and made the Strategies/
    Backtesting pages feel like they'd hung on load.

    `recent_batches` is fetched once by the caller and reused across every
    strategy in the list -- list_strategies() used to call
    storage.list_recent_batches(limit=100) freshly inside this function for
    EVERY strategy (a DB round trip + JSON-parsing up to 100 batches, N
    times over for N strategies), which is exactly the kind of redundant
    per-item query this endpoint is also polled by the Paper Trading page
    load (it lists available strategies), so it compounds with everything
    else fetched on that page.

    Master Task 4, Phase 1.2: `recent_batches` is a fixed-size GLOBAL
    window (the 100 most recent batches across every strategy, including
    the Evolution/Self-Learning/SINDHU Generator's own continuous stream of
    candidate backtests). Audited live: with that background volume, a
    real manually-built strategy's own last completed batch routinely ages
    out of the top 100 within a day even though nothing about the
    strategy's own results changed -- confirmed on the live database (128
    of 154 real strategies showed no match in the 100-most-recent window
    despite most having a real completed batch further back). Falls back
    to a direct, indexed, strategy-specific lookup
    (storage.latest_completed_batch_for_strategy_name, already used
    elsewhere for the same name-based best-effort link) instead of
    silently returning None -- this only ever runs for the strategies the
    fast global-window pass didn't already find, so the common case pays
    no extra query."""
    for batch in recent_batches:
        if batch["strategy_name"] != strategy_name:
            continue
        return _batch_result_summary(batch, batch_results_cache)

    fallback_batch_id = storage.latest_completed_batch_for_strategy_name(strategy_name)
    if not fallback_batch_id:
        return None
    fallback_batch = storage.get_batch(fallback_batch_id)
    if not fallback_batch:
        return None
    return _batch_result_summary(fallback_batch, batch_results_cache)


def _batch_result_summary(batch, batch_results_cache=None):
    if batch["status"] != "completed":
        return {"batch_id": batch["batch_id"], "status": batch["status"], "created_at": batch["created_at"]}
    if batch_results_cache is not None and batch["batch_id"] in batch_results_cache:
        results = batch_results_cache[batch["batch_id"]]
    else:
        results = storage.get_batch_results(batch["batch_id"])
        if batch_results_cache is not None:
            batch_results_cache[batch["batch_id"]] = results
    completed = [r for r in results if r["status"] == "completed" and r["metrics"]]
    if not completed:
        return {"batch_id": batch["batch_id"], "status": "completed", "created_at": batch["created_at"], "total_trades": 0}
    total_trades = sum(r["metrics"]["total_trades"] for r in completed)
    wins = sum(r["metrics"]["wins"] for r in completed)
    return {
        "batch_id": batch["batch_id"], "status": "completed", "created_at": batch["created_at"],
        "total_trades": total_trades, "symbols_tested": len(completed),
        "win_rate": round((wins / total_trades * 100) if total_trades else 0.0, 2),
        "avg_profit_pct": round(sum(r["metrics"]["profit_pct"] for r in completed) / len(completed), 2),
    }


def _condition_roles_summary(cfg):
    """[{bucket, type, name, direction, role}] for every concept condition
    -- lets the Strategies page show which declared timeframe (bias/trend/
    analysis/entry) each condition actually reads from, instead of that
    being invisible plumbing. role is always a real value here (never
    null) -- unset means the entry-timeframe default, shown explicitly so
    the CEO isn't left guessing whether it was never checked or is
    deliberately on entry."""
    out = []
    for bucket in ("entry_conditions", "long_entry_conditions", "short_entry_conditions",
                   "exit_conditions", "confirmation_conditions"):
        for cond in getattr(cfg, bucket, []):
            if cond.type == "concept":
                out.append({
                    "bucket": bucket, "name": cond.name, "direction": cond.direction,
                    "role": cond.role or "entry",
                })
            elif cond.type == "indicator_vs_indicator":
                p1 = (cond.params or {}).get("period")
                p2 = (cond.params2 or {}).get("period")
                out.append({
                    "bucket": bucket, "name": f"{cond.indicator}{p1 or ''} {cond.op} {cond.indicator2}{p2 or ''}",
                    "direction": None, "role": cond.role or "entry",
                })
    return out


def _compute_strategies_list(q, include_archived=False):
    # Batch 4, Task 3: an archived strategy (a resolved duplicate) stays in
    # the library in full -- reversible, never deleted -- but drops out of
    # the normal browsing list unless explicitly requested (include_archived,
    # used by the "Show Archived" toggle to make the archive reversible in
    # practice, not just in the API). lib.list_all()/search() themselves are
    # untouched so every other subsystem (paper trading, evolution, scripts)
    # keeps seeing it exactly as before.
    strategies = lib.search(q) if include_archived else [m for m in lib.search(q) if not m.get("archived")]
    recent_batches = storage.list_recent_batches(limit=100)
    # Batch 3, Task 3: one bulk query for every strategy's lock status
    # instead of one round-trip per strategy in the loop below -- this
    # list is polled/loaded frequently, and N separate small queries
    # measured 130+ seconds under real DB load (other writers holding the
    # SQLite file busy) versus a single query.
    lock_statuses = extraction_lock.check_strategy_locks_bulk([m["id"] for m in strategies])
    # Batch 4, Task 1: _strategy_last_batch_result and evaluate_strategy_
    # performance each independently fetch storage.get_batch_results() for
    # the SAME batch_id when a strategy has one -- this shared dict lets the
    # second call reuse the first's result instead of opening a second DB
    # connection, halving that part of the endpoint's real DB round trips.
    batch_results_cache = {}
    for meta in strategies:
        try:
            cfg = lib.load(meta["id"])
            meta["concepts_used"] = cfg.concepts_used
            meta["timeframes"] = cfg.timeframes
            validator_errors = validate(cfg)
            safety = run_safety_check(cfg)
            # Automatic Strategy Safety Check (computed live, not from the
            # cached meta.json value, so the list is never stale even for a
            # strategy saved before this check existed and not yet
            # backfilled): validator errors (missing/invalid fields) take
            # priority since those block backtesting outright; a strategy
            # that's structurally valid but fails the safety check is
            # "Needs Review", not silently shown as ready.
            if validator_errors:
                meta["status"] = "NEEDS_CLARIFICATION"
            elif not safety["passed"]:
                meta["status"] = "NEEDS_REVIEW"
            else:
                meta["status"] = "READY_FOR_BACKTEST"
            meta["safety_reasons"] = safety["reasons"]
            meta["condition_roles"] = _condition_roles_summary(cfg)
        except Exception:
            meta["concepts_used"], meta["timeframes"], meta["status"] = [], {}, "NEEDS_CLARIFICATION"
            meta["safety_reasons"] = []
            meta["condition_roles"] = []
        meta["last_batch_result"] = _strategy_last_batch_result(
            meta["name"], recent_batches, batch_results_cache=batch_results_cache)
        lock_status = lock_statuses.get(meta["id"], {"locked": False, "overridden": False})
        meta["extraction_locked"] = lock_status["locked"]
        meta["extraction_overridden"] = lock_status["overridden"]
        # Strategy Performance Dashboard (display-only -- reads already-
        # computed backtest/walk-forward results, never runs anything, never
        # blocks or removes a strategy): a single GREEN/RED verdict combining
        # expectancy, profit factor, trade count, and Walk-Forward status.
        try:
            performance = evaluate_strategy_performance(
                meta["id"], recent_batches=recent_batches, batch_results_cache=batch_results_cache)
        except Exception:
            performance = None
        meta["performance_verdict"] = performance["verdict"] if performance else None
        meta["performance_label"] = performance["label"] if performance else None
        meta["performance_failed_factors"] = performance["failed_factors"] if performance else []

        # Master Task 3, Phase 0.7: opportunistically refresh this
        # strategy's git-tracked backtest snapshot (see strategy_library.
        # save_backtest_snapshot's docstring) using numbers already
        # computed above -- no extra queries.
        lbr = meta["last_batch_result"]
        if lbr and lbr.get("status") == "completed" and lbr.get("total_trades"):
            profit_factor = next(
                (f["value"] for f in (performance["factors"] if performance else []) if f["factor"] == "profit_factor"),
                None,
            )
            try:
                lib.save_backtest_snapshot(meta["id"], {
                    "win_rate": lbr.get("win_rate"),
                    "profit_factor": profit_factor,
                    "total_trades": lbr.get("total_trades"),
                    "batch_id": lbr.get("batch_id"),
                    "computed_at": lbr.get("created_at"),
                })
            except Exception:
                pass
    return strategies


# Batch 4, Task 1: this endpoint is polled by both the Strategies and Paper
# Trading pages and was measured taking 30-60+ seconds under real DB write
# contention -- see get_conn()'s synchronous=NORMAL fix for the underlying
# cause. A short stale-while-revalidate cache (sindhu_web.cache, the same
# pattern /api/home already uses) means only the very first cold call per
# TTL window pays that cost; every poll within the window gets the last
# computed snapshot instantly. Only the no-search-term case (q="") is
# cached -- that's the one actually hammered by repeated page polls: the
# search box is a deliberate one-off user action where a stale result would
# be actively misleading, so q != "" always computes fresh. save_strategy()
# below explicitly invalidates this key so a newly created/edited strategy
# is never hidden behind a stale cache entry.
_STRATEGIES_CACHE_KEY = "strategies_list:all"
_STRATEGIES_CACHE_TTL = 10


@router.get("/api/backtesting/strategies")
def list_strategies(q: str = "", include_archived: bool = False):
    if q or include_archived:
        return {"strategies": _compute_strategies_list(q, include_archived=include_archived)}
    return {"strategies": cache.cached(
        _STRATEGIES_CACHE_KEY, _STRATEGIES_CACHE_TTL, lambda: _compute_strategies_list(""))}


@router.get("/api/backtesting/strategies/{strategy_id}/versions")
def get_strategy_versions(strategy_id: str):
    return {"versions": lib.version_history(strategy_id)}


@router.get("/api/backtesting/strategies/{strategy_id}/claim-check")
def get_strategy_claim_check(strategy_id: str):
    """Item 7 (Cross-Reference Validation): compares this strategy's own
    source-document performance claim (captured at import time -- see
    ai_integration.claim_extraction) against its real, latest completed
    backtest result. Reuses the exact same "latest batch by strategy name"
    lookup and quick_batch_summary() that /api/reports/best-worst/strategies
    already uses, so this never disagrees with what the rest of the app
    shows as this strategy's real performance."""
    from backtest_engine.claim_validation import compare_claim_to_backtest
    from backtest_engine.reports import quick_batch_summary

    try:
        cfg = lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")

    if cfg.claimed_win_rate_pct is None:
        return {"has_claim": False}

    actual_win_rate_pct, actual_trade_count = None, None
    for b in storage.list_recent_batches(limit=200):
        if b["status"] != "completed" or b["strategy_name"] != cfg.name:
            continue
        summary = quick_batch_summary(b["batch_id"])
        if summary and summary.get("total_trades"):
            actual_win_rate_pct = summary["win_rate"]
            actual_trade_count = summary["total_trades"]
            break  # list_recent_batches is newest-first -- this is the latest result

    result = compare_claim_to_backtest(cfg.claimed_win_rate_pct, actual_win_rate_pct, actual_trade_count)
    result["claim_source_text"] = cfg.claimed_win_rate_source_text
    return result


@router.get("/api/backtesting/strategies/{strategy_id}/versions/{version_a}/diff/{version_b}")
def get_strategy_version_diff(strategy_id: str, version_a: int, version_b: int):
    """Item 6 (Extraction History/Versioning): what actually changed
    between two saved versions of the same strategy -- both versions are
    full snapshots already kept forever (strategies/library/<id>/versions/),
    this just reads two of them and reports the field-level differences
    instead of making the user diff two raw JSON files by hand."""
    try:
        changes = lib.diff_versions(strategy_id, version_a, version_b)
    except FileNotFoundError:
        raise HTTPException(404, "strategy or version not found")
    return {"strategy_id": strategy_id, "version_a": version_a, "version_b": version_b, "changes": changes}


class RestoreVersionRequest(BaseModel):
    version: int


@router.post("/api/backtesting/strategies/{strategy_id}/restore-version")
def restore_strategy_version(strategy_id: str, req: RestoreVersionRequest):
    """Grand Feature Expansion, Phase 4 Feature 22: Undo/Rollback UI Config
    -- restores an older saved version as a new current version. Never
    deletes anything; the old version file and every version in between
    stay on disk forever, same as every other edit to this strategy."""
    try:
        new_version = lib.restore_version(strategy_id, req.version)
    except FileNotFoundError:
        raise HTTPException(404, "strategy or version not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    cache.invalidate(_STRATEGIES_CACHE_KEY)
    sync.notify("strategy", "version_restored", f"Restored version {req.version} as new version {new_version}", id=strategy_id)
    return {"ok": True, "new_version": new_version}


# --------------------------------------------------------------- Batch 4, Task 3: Duplicate Strategy Cleanup

def _rule_count_for(strategy_id, cfg, fidelity_reports):
    """Best available "how many rules this one captured" number: the real
    AI extraction fidelity count (Batch 3) when this strategy went through
    that pipeline, otherwise a count of its actual parsed conditions --
    never a guess."""
    report = fidelity_reports.get(strategy_id)
    if report:
        return report["captured_rule_count"]
    return (
        len(cfg.entry_conditions) + len(cfg.long_entry_conditions) + len(cfg.short_entry_conditions)
        + len(cfg.exit_conditions) + len(cfg.confirmation_conditions)
    )


@router.get("/api/backtesting/duplicates")
def get_duplicate_strategy_groups():
    """Surfaces the SAME DNA-fingerprint duplicate detection already used
    at import time (knowledge_compiler.quality.strategy_dna -- no new
    detection logic here) as an actionable, grouped view: every strategy
    currently in the library that shares an identical DNA with at least
    one other active (non-archived) strategy, with enough plain-language
    info per copy (when imported, how many rules it captured, its most
    recent backtest) to choose which to keep."""
    groups = kc_quality.find_duplicate_strategy_groups(lib.list_all, lib.load)
    if not groups:
        return {"groups": []}

    all_ids = [sid for g in groups for sid in g["strategy_ids"]]
    fidelity_reports = storage.get_latest_extraction_fidelity_reports_for_strategies(all_ids)
    recent_batches = storage.list_recent_batches(limit=100)
    batch_results_cache = {}
    meta_by_id = {m["id"]: m for m in lib.list_all()}

    result_groups = []
    for g in groups:
        members = []
        for sid in g["strategy_ids"]:
            meta = meta_by_id.get(sid)
            if meta is None:
                continue
            try:
                cfg = lib.load(sid)
            except FileNotFoundError:
                continue
            members.append({
                "id": sid,
                "name": meta["name"],
                "imported_at": meta.get("created_at"),
                "rule_count": _rule_count_for(sid, cfg, fidelity_reports),
                "last_batch_result": _strategy_last_batch_result(
                    meta["name"], recent_batches, batch_results_cache=batch_results_cache),
            })
        if len(members) >= 2:
            result_groups.append({"dna": g["dna"], "strategies": members})
    return {"groups": result_groups}


class ArchiveRequest(BaseModel):
    confirm: bool = False


@router.post("/api/backtesting/strategies/{strategy_id}/archive")
def archive_strategy(strategy_id: str, req: ArchiveRequest):
    """Archives (never deletes) one strategy as a resolved duplicate.
    Blocks archiving the LAST remaining active copy of a DNA group --
    this endpoint exists to clean up redundant copies, not to make an
    idea disappear from the library entirely, and that's exactly what
    "never remove the copy the CEO chooses to keep" means enforced
    server-side rather than only trusted to the frontend."""
    if not req.confirm:
        raise HTTPException(400, "Confirmation required -- pass confirm: true to archive this strategy.")
    try:
        cfg = lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")
    dna = kc_quality.strategy_dna(cfg)
    active_siblings = [
        m["id"] for m in lib.list_all()
        if not m.get("archived") and m["id"] != strategy_id
        and kc_quality.strategy_dna(lib.load(m["id"])) == dna
    ]
    if not active_siblings:
        raise HTTPException(
            400,
            "Yeh is group ki AAKHRI active copy hai -- isay archive nahi kar sakte, "
            "warna is strategy ka koi record active nahi bachega. Pehle koi doosri copy rakhein.",
        )
    lib.set_archived(strategy_id, True)
    cache.invalidate(_STRATEGIES_CACHE_KEY)
    sync.notify("strategy", "archived", f"Strategy archived (duplicate cleanup): {cfg.name}", id=strategy_id)
    return {"ok": True, "id": strategy_id, "archived": True}


@router.post("/api/backtesting/strategies/{strategy_id}/unarchive")
def unarchive_strategy(strategy_id: str):
    """Always allowed -- restoring an archived strategy back into normal
    browsing can never make things worse, so it needs no confirmation
    step beyond the click itself."""
    try:
        lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")
    lib.set_archived(strategy_id, False)
    cache.invalidate(_STRATEGIES_CACHE_KEY)
    sync.notify("strategy", "unarchived", "Strategy restored from archive", id=strategy_id)
    return {"ok": True, "id": strategy_id, "archived": False}


# --------------------------------------------------------------- Batch 3, Task 3: Verification View + Incomplete Lock

class ExtractionOverrideRequest(BaseModel):
    overridden: bool


@router.get("/api/backtesting/strategies/{strategy_id}/extraction-verification")
def get_extraction_verification(strategy_id: str, lang: str = "ur"):
    """Side-by-side view data (Task 3): each row is the user's own
    document text next to a plain-language description of what was
    understood (Roman Urdu by default, English when lang="en" -- Batch 5,
    Task 3), plus a captured/missing mark and an overall plain-language
    summary. Also whether this strategy is currently locked out of
    backtesting/optimization/paper trading."""
    try:
        lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")
    return extraction_lock.verification_summary(strategy_id, lang=lang if lang == "en" else "ur")


@router.post("/api/backtesting/strategies/{strategy_id}/extraction-override")
def set_extraction_override(strategy_id: str, req: ExtractionOverrideRequest, lang: str = "ur"):
    """The explicit "test anyway" override -- persistent, so every
    backtest/optimize/paper-trading run for this strategy from now on
    (until un-overridden) is permitted but permanently tagged with a
    visible warning (extraction_override_warning on the resulting
    batches)."""
    try:
        lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")
    report = storage.get_extraction_fidelity_report_for_strategy(strategy_id)
    if report is None:
        msg = ("This strategy has no verification report -- there's nothing to override." if lang == "en"
               else "Is strategy ka koi verification report nahi hai -- override karne ki zaroorat nahi.")
        raise HTTPException(400, msg)
    extraction_lock.set_override(strategy_id, req.overridden)
    sync.notify("strategy", "extraction_override_changed",
                f"{'Override ON' if req.overridden else 'Override OFF'} for {strategy_id}", id=strategy_id)
    return extraction_lock.verification_summary(strategy_id, lang=lang if lang == "en" else "ur")


@router.post("/api/backtesting/strategies/{strategy_id}/extraction-audit")
def run_extraction_audit(strategy_id: str, lang: str = "ur"):
    """Retroactive audit (Task 3, requirement 5): runs the SAME multi-pass
    + auto-retry pipeline (Tasks 1/2) against an already-saved strategy's
    original document text, for strategies imported before this feature
    existed (no report yet) or a CEO-requested re-check. Real AI calls --
    not instant, and subject to the same provider fallback chain/quota as
    any other extraction."""
    try:
        cfg = lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")
    if not cfg.raw_text or not cfg.raw_text.strip():
        msg = ("This strategy's original document text was not saved -- an audit isn't possible." if lang == "en"
               else "Is strategy ka original document text save nahi hai -- audit nahi ho sakta.")
        raise HTTPException(400, msg)

    content_hash = hashlib.sha256(cfg.raw_text.strip().lower().encode("utf-8")).hexdigest()
    mp = sentence_level_extraction.run_sentence_level_extraction(cfg.raw_text, content_type="strategy")
    now_iso = _now_iso()
    storage.save_extraction_fidelity_report(
        content_hash, mp["comparison"]["expected_count"], mp["comparison"]["captured_count"],
        mp["call_count"], mp["comparison"]["rules"], mp["provider"], now_iso, retry_count=mp["retry_count"],
    )
    storage.set_extraction_fidelity_strategy_id(content_hash, strategy_id)
    sync.notify("strategy", "extraction_audited",
                f"Verification check done for {cfg.name}: {mp['comparison']['captured_count']}/{mp['comparison']['expected_count']} rules understood",
                id=strategy_id)
    return extraction_lock.verification_summary(strategy_id, lang=lang if lang == "en" else "ur")


@router.get("/api/backtesting/strategies/{strategy_id}")
def get_strategy(strategy_id: str):
    try:
        cfg = lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")
    # Includes the same validity check the strategy list uses -- the
    # Backtesting page needs this to show an accurate preview right after
    # Load without re-parsing raw_text (see frontend comment for why that's
    # unsafe for AI-imported strategies).
    errors = validate(cfg)
    safety = run_safety_check(cfg)
    performance = evaluate_strategy_performance(strategy_id)
    return {
        "config": cfg.to_dict(), "errors": errors, "valid": not errors,
        "safety_status": safety["status"], "safety_reasons": safety["reasons"],
        "performance": performance,
    }


@router.delete("/api/backtesting/strategies/{strategy_id}")
def delete_strategy(strategy_id: str):
    lib.delete(strategy_id)
    sync.notify("strategy", "deleted", "Strategy deleted", id=strategy_id)
    return {"ok": True}


@router.post("/api/backtesting/strategies/{strategy_id}/favourite")
def favourite_strategy(strategy_id: str, favourite: bool = True):
    lib.set_favourite(strategy_id, favourite)
    sync.notify("strategy", "updated", "Strategy favourite toggled", id=strategy_id)
    return {"ok": True}


class TagsRequest(BaseModel):
    tags: list[str]


@router.post("/api/backtesting/strategies/{strategy_id}/tags")
def set_strategy_tags(strategy_id: str, req: TagsRequest):
    """Grand Feature Expansion, Phase 4 Feature 3: Strategy Tagging System.
    lib.set_tags() itself already existed (used internally at creation
    time for system tags like "dual_tp_variant") but had no endpoint or
    UI ever calling it for user-defined tags -- this is that missing
    wiring, reusing the existing function as-is."""
    tags = [t.strip() for t in req.tags if t.strip()]
    lib.set_tags(strategy_id, tags)
    sync.notify("strategy", "updated", f"Strategy tags updated: {', '.join(tags) or '(cleared)'}", id=strategy_id)
    cache.invalidate(_STRATEGIES_CACHE_KEY)
    return {"ok": True, "tags": tags}


class CommentRequest(BaseModel):
    comment: str = ""


@router.post("/api/backtesting/strategies/{strategy_id}/comment")
def set_strategy_comment(strategy_id: str, req: CommentRequest):
    """Grand Feature Expansion, Phase 4 Feature 9: Strategy Comments/Notes
    -- a freeform field, distinct from the system-generated clarification
    notes list."""
    lib.set_comment(strategy_id, req.comment)
    sync.notify("strategy", "updated", "Strategy comment updated", id=strategy_id)
    cache.invalidate(_STRATEGIES_CACHE_KEY)
    return {"ok": True, "comment": req.comment}


@router.post("/api/backtesting/strategies/{strategy_id}/duplicate")
def duplicate_strategy(strategy_id: str):
    new_id = lib.duplicate(strategy_id)
    sync.notify("strategy", "created", "Strategy duplicated", id=new_id)
    return {"id": new_id}


@router.get("/api/backtesting/coins")
def list_coins():
    exchange = _default_exchange()
    return {"exchange": exchange, "symbols": storage.load_symbols(exchange)}


# --------------------------------------------------------------- Monte Carlo Engine (Group 6 #4)

@router.get("/api/backtesting/monte-carlo/{batch_id}")
def get_monte_carlo(batch_id: str, iterations: int = 1000):
    return monte_carlo.run_monte_carlo(batch_id, iterations=iterations)


# ----------------------------------------- Sanity Check Alert (Grand Feature Expansion, Phase 3 Feature 1)

@router.get("/api/backtesting/plausibility/{batch_id}")
def get_batch_plausibility(batch_id: str):
    """On-demand check (the hourly background sweep -- see
    backtest_engine/result_plausibility.py -- covers this automatically,
    but this lets the CEO check a batch immediately after it finishes
    instead of waiting)."""
    return result_plausibility.check_batch_plausibility(batch_id)


# ----------------------------------------- Slippage Sensitivity Test (Grand Feature Expansion, Phase 3 Feature 18)

@router.get("/api/backtesting/slippage-sensitivity/{batch_id}")
def get_slippage_sensitivity(batch_id: str):
    return slippage_sensitivity.run_slippage_sensitivity_test(batch_id)


# ----------------------------------------- Session Time-Tracker (Grand Feature Expansion, Phase 3 Feature 14)

@router.get("/api/backtesting/duration-stats")
def get_duration_stats(limit: int = 100):
    return duration_tracker.compute_duration_stats(limit=limit)


# ----------------------------------------- Historical What-If Simulator (Grand Feature Expansion, Phase 5 Feature 14)

class WhatIfRequest(BaseModel):
    batch_id: str
    parameter_changes: dict
    max_symbols: int = 3


@router.post("/api/backtesting/what-if")
def run_what_if_simulation(req: WhatIfRequest):
    """A fast, bounded (~30 days, up to 5 symbols) real re-simulation with
    one or more parameters changed -- e.g. {"risk_pct": 2.0} or
    {"stop_loss": {"type": "fixed_pct", "value": 2.0}}. Never touches the
    strategy's own saved config or the original batch's results; purely a
    what-if preview. Takes only batch_id (not a strategy_id) since the
    Backtest History page -- the natural place to run this from -- only
    ever has the batch in hand; the strategy is resolved from the batch's
    own recorded strategy_name (same "latest/matching batch by strategy
    name" style lookup used elsewhere in this codebase, e.g.
    get_strategy_claim_check above)."""
    batch = storage.get_batch(req.batch_id)
    if not batch:
        raise HTTPException(404, "batch not found")
    meta = next((m for m in lib.list_all() if m["name"] == batch["strategy_name"]), None)
    if not meta:
        raise HTTPException(404, "the strategy this batch belongs to no longer exists in the library")
    cfg = lib.load(meta["id"])
    try:
        result = what_if_simulator.run_what_if(cfg, batch, req.parameter_changes, max_symbols=req.max_symbols)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, f"invalid parameter_changes: {e}")
    if result is None:
        raise HTTPException(400, "this batch has no usable symbol list / date range to replay against")
    return result


# ----------------------------------------- Feature Importance Ranking (Grand Feature Expansion, Phase 6 Feature 6)

class FeatureImportanceRequest(BaseModel):
    batch_id: str
    max_symbols: int = 3


@router.post("/api/backtesting/feature-importance")
def run_feature_importance(req: FeatureImportanceRequest):
    """Which of THIS strategy's own entry/confirmation conditions actually
    drive its performance, via leave-one-out ablation against the same
    fast, bounded window/symbol-count Historical What-If Simulator uses.
    Resolves the strategy from the batch's own recorded strategy_name,
    same pattern as the What-If Simulator endpoint above."""
    batch = storage.get_batch(req.batch_id)
    if not batch:
        raise HTTPException(404, "batch not found")
    meta = next((m for m in lib.list_all() if m["name"] == batch["strategy_name"]), None)
    if not meta:
        raise HTTPException(404, "the strategy this batch belongs to no longer exists in the library")
    cfg = lib.load(meta["id"])
    result = feature_importance.rank_feature_importance(cfg, batch, max_symbols=req.max_symbols)
    if result is None:
        raise HTTPException(400, "this batch has no usable symbol list / date range to replay against")
    return result


# ----------------------------------------- Cross-Coin Group Validation (Grand Feature Expansion, Phase 6 Feature 8)

@router.get("/api/backtesting/cross-coin-validation/{batch_id}")
def get_cross_coin_validation(batch_id: str):
    """Whether this batch's real per-coin results hold up similarly across
    low/medium/high VOLATILITY groups (computed fresh from real data every
    time, never a hardcoded coin list) -- distinct from the flat per-coin
    ranking table, which shows every coin individually with no grouping."""
    result = cross_coin_validation.validate_across_coin_groups(batch_id)
    if result is None:
        raise HTTPException(404, "batch not found")
    return result


# ----------------------------------------- Self-Generated Strategy Variants (Grand Feature Expansion, Phase 6 Feature 5)

class StrategyVariantsRequest(BaseModel):
    batch_id: str
    max_variants: int = strategy_variants.MAX_VARIANTS
    max_symbols: int = 3


@router.post("/api/backtesting/strategy-variants")
def run_strategy_variants(req: StrategyVariantsRequest):
    """Branches several PARALLEL sibling variants off this strategy (each
    swapping one concept-type entry condition for a same-DNA-category
    alternative) and tests them side-by-side against the same fast,
    bounded window/symbol-count as the What-If Simulator and Feature
    Importance Ranking above. Never touches the CEO's real saved config --
    every variant is a throwaway clone."""
    batch = storage.get_batch(req.batch_id)
    if not batch:
        raise HTTPException(404, "batch not found")
    meta = next((m for m in lib.list_all() if m["name"] == batch["strategy_name"]), None)
    if not meta:
        raise HTTPException(404, "the strategy this batch belongs to no longer exists in the library")
    cfg = lib.load(meta["id"])
    result = strategy_variants.test_variants(cfg, batch, max_variants=req.max_variants, max_symbols=req.max_symbols)
    if result is None:
        raise HTTPException(400, "this batch has no usable symbol list / date range to replay against")
    return result


# --------------------------------------------------------------- Stress Testing Engine (B5)

@router.get("/api/backtesting/stress-test/{strategy_id}/{symbol}")
def get_stress_test(strategy_id: str, symbol: str):
    exchange = _default_exchange()
    return stress_test.run_stress_test(strategy_id, exchange, symbol)


# --------------------------------------------------------------- Genetic Optimization Engine (B6)

@router.get("/api/backtesting/genetic-optimize/{strategy_id}/{symbol}")
def get_genetic_optimize(strategy_id: str, symbol: str, days: int = 30,
                          population_size: int = 10, generations: int = 5):
    """Runs BOTH the existing grid-search optimizer and the new genetic
    optimizer on the exact same strategy/symbol/date-window, so the two
    can be directly compared. Neither writes anything to the database --
    same in-memory-only contract _run_in_memory already guarantees."""
    exchange = _default_exchange()
    min_ms, max_ms = storage.get_symbol_time_bounds(exchange, symbol)
    if min_ms is None:
        return {"available": False, "reason": f"no stored data for {symbol}"}
    start_ms = max(min_ms, max_ms - days * 86400 * 1000)
    end_ms = max_ms

    try:
        cfg = lib.load(strategy_id)
    except Exception as e:
        return {"available": False, "reason": f"could not load strategy: {e!r}"}

    settings = {"initial_balance": 10000.0}

    best_cfg, tried_log, best_description = grid_optimizer.optimize(cfg, exchange, symbol, settings, start_ms, end_ms)
    grid_metrics = None
    if best_cfg is not None:
        grid_metrics = grid_optimizer._run_in_memory(best_cfg, exchange, symbol, settings, start_ms, end_ms)
    grid_result = {
        "candidates_tried": len(tried_log), "best_description": best_description,
        "best_metrics": grid_metrics,
    }

    genetic_result = genetic_optimizer.run_genetic_optimization(
        cfg, exchange, symbol, settings, start_ms, end_ms,
        population_size=population_size, generations=generations,
    )

    return {"available": True, "strategy_id": strategy_id, "symbol": symbol,
            "window_days": days, "grid_search": grid_result, "genetic": genetic_result}


# --------------------------------------------------------------- Trade Audit Engine (Group 6 #5)

@router.get("/api/backtesting/trade-audit/{batch_id}/{symbol}/{timeframe}/{trade_num}")
def get_trade_audit(batch_id: str, symbol: str, timeframe: str, trade_num: int):
    """Full manual-verification detail for one backtest trade: the exact
    entry/exit rule that fired (already recorded at trade time, not
    re-derived), and the raw 1-minute candles spanning the trade so the
    entry/exit prices can be checked against real market data by hand."""
    trades = storage.get_trades(batch_id, symbol=symbol, timeframe=timeframe)
    trade = next((t for t in trades if t["trade_num"] == trade_num), None)
    if not trade:
        raise HTTPException(404, "trade not found")

    exchange = _default_exchange()
    start_ms = trade["entry_time"] - 30 * 60 * 1000  # 30min padding before entry
    end_ms = (trade["exit_time"] or trade["entry_time"]) + 30 * 60 * 1000
    try:
        df = get_ohlcv(exchange, symbol, interval="1m", start_ms=start_ms, end_ms=end_ms)
        candles = [
            {"time": int(idx.timestamp() * 1000), "open": row.open, "high": row.high,
             "low": row.low, "close": row.close, "volume": row.volume}
            for idx, row in df.iterrows()
        ]
    except Exception:
        candles = []

    return {"trade": trade, "candles": candles}


# ----------------------------------------- Backtest Replay Visualizer (Grand Feature Expansion, Phase 5 Feature 15)

MAX_REPLAY_BARS = 2000


@router.get("/api/backtesting/replay/{batch_id}/{symbol}")
def get_backtest_replay(batch_id: str, symbol: str):
    """A full-run, bar-by-bar replay of one symbol's real backtest bars
    plus every real trade on it -- distinct from the Trade Audit above
    (one static candle window per SELECTED trade) and from the desktop
    dashboard's own TradeReplayDialog (also per-trade snapshots, PySide6,
    not this web app). The timeframe is read from this symbol's own real
    trades (an MTF strategy has exactly one entry timeframe), not raw 1m,
    so a multi-month run stays a renderable number of bars -- capped at
    MAX_REPLAY_BARS regardless, with the trade list unaffected (every real
    trade on this symbol is returned, even ones outside the candle window)."""
    batch = storage.get_batch(batch_id)
    if not batch:
        raise HTTPException(404, "batch not found")
    trades = storage.get_trades(batch_id, symbol=symbol)
    if not trades:
        raise HTTPException(404, "no trades recorded for this symbol in this batch")
    timeframe = trades[0]["timeframe"]

    settings = batch.get("settings") or {}
    start_ms, end_ms = settings.get("start_ms"), settings.get("end_ms")
    if start_ms is None or end_ms is None:
        raise HTTPException(400, "this batch has no recorded date range to replay")

    exchange = batch["exchange"]
    df = get_ohlcv(exchange, symbol, interval=timeframe, start_ms=start_ms, end_ms=end_ms)
    if len(df) > MAX_REPLAY_BARS:
        df = df.tail(MAX_REPLAY_BARS)
    candles = [
        {"time": int(idx.timestamp() * 1000), "open": row.open, "high": row.high,
         "low": row.low, "close": row.close}
        for idx, row in df.iterrows()
    ]
    return {"symbol": symbol, "timeframe": timeframe, "candles": candles, "trades": trades,
            "truncated": len(df) >= MAX_REPLAY_BARS}


class RunRequest(BaseModel):
    strategy_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    symbols: Optional[List[str]] = None
    all_coins: bool = True
    initial_balance: float = 1000.0
    risk_pct: Optional[float] = None
    commission_pct: float = 0.1
    slippage_pct: float = 0.05
    position_size_pct: float = 10.0
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    use_multiprocessing: bool = True
    lang: str = "ur"


@router.post("/api/backtesting/run")
def run_backtest(req: RunRequest):
    running = job_manager.get_running_job_of_kind("backtest")
    if running is not None:
        p = running.progress or {}
        done = p.get("done")
        total = p.get("total")
        strategy_name = p.get("current_strategy") or "a strategy"
        progress_desc = f"{done}/{total} coins" if done is not None and total is not None else "in progress"
        raise HTTPException(
            409,
            f"A backtest is already running ({strategy_name}, {progress_desc}). "
            f"Please wait for it to finish or stop it first (job {running.id}).",
        )

    if req.strategy_id:
        cfg = lib.load(req.strategy_id)
    elif req.config:
        cfg = StrategyConfig.from_dict(req.config)
    else:
        raise HTTPException(400, "strategy_id or config required")

    # Batch 3, Task 3: Incomplete Lock -- a strategy with rules the
    # system still couldn't understand (after Task 2's retries) is
    # blocked here, before any real backtest work starts, unless the CEO
    # already explicitly overrode it (see /api/strategies/{id}/
    # extraction-override). Plain Roman Urdu/Hinglish message, no jargon.
    extraction_override_warning = False
    if req.strategy_id:
        lock_status = extraction_lock.check_strategy_lock(req.strategy_id)
        if lock_status["locked"]:
            raise HTTPException(423, extraction_lock.lock_message(lock_status, lang=req.lang if req.lang == "en" else "ur"))
        extraction_override_warning = lock_status["overridden"] and bool(lock_status["missing_rules"])

    # Strategy Wizard: a condition the user marked "bilkul naya" (couldn't be
    # matched to any known concept) is saved verbatim but must never
    # silently execute unverified logic -- same "don't run until resolved"
    # rule as the Incomplete Lock above, just for a Wizard-built condition
    # instead of an unclear parsed rule.
    if wizard.has_manual_review(cfg):
        items = wizard.list_manual_review_conditions(cfg)
        names = "; ".join(c.raw_source or c.text or "?" for c in items[:5])
        raise HTTPException(
            423,
            f"Is strategy mein {len(items)} condition(s) abhi tak Manual Review mein hain "
            f"(koi bhi maloom concept se match nahi hui): {names}. Backtest chalane se pehle "
            f"in conditions ko Strategy Wizard mein resolve karein.",
        )

    errors = validate(cfg)
    if errors:
        raise HTTPException(400, {"errors": errors})

    exchange = _default_exchange()
    symbols = req.symbols if (req.symbols and not req.all_coins) else storage.load_symbols(exchange)
    if not symbols:
        raise HTTPException(400, "no coins available for this exchange")

    settings = {
        "initial_balance": req.initial_balance,
        "risk_pct": req.risk_pct or cfg.risk_pct or 1.0,
        "commission_pct": req.commission_pct,
        "slippage_pct": req.slippage_pct,
        "position_size_pct": req.position_size_pct,
        "start_ms": req.start_ms, "end_ms": req.end_ms,
    }

    # Part 3: a fast 1-2 coin / short-date-range check BEFORE committing to
    # the full (potentially 50-coin) run below -- catches a structural
    # 0-trade strategy (a condition that never fires even once) right away
    # instead of after the whole backtest finishes.
    sanity = sanity_check.run_sanity_check(cfg.to_dict(), exchange, symbols, settings)
    if not sanity["ok"]:
        raise HTTPException(400, {
            "errors": [sanity["reason"]],
            "diagnosis": sanity["diagnosis"],
            "sanity_check_failed": True,
        })

    control = DownloadControl()
    job_id = uuid.uuid4().hex[:12]

    def _progress_cb(done, total, symbol, timeframe, stage=None, bar_pct=None,
                      trades_so_far=None, eta_seconds=None):
        job_manager.update_progress(
            job_id, done=done, total=total, current_coin=symbol,
            current_timeframe=timeframe, current_strategy=cfg.name,
            current_stage=stage, bar_pct=bar_pct,
            trades_so_far=trades_so_far, eta_seconds=eta_seconds,
        )

    # Running trade stats (total/wins/cumulative pnl/peak/drawdown/equity
    # curve) used to be tracked ONLY in the browser tab's own JS variables,
    # rebuilt one WebSocket "last_trade" event at a time -- fine while the
    # tab stays open, but navigating away and back created a fresh
    # renderBacktesting() call with those variables reset to zero, even
    # though the backtest was still running fine server-side. job.progress
    # already persisted done/total/current_coin/etc, but never the trade
    # aggregates, so those specific fields looked "reset" on return. Kept
    # here (not in job_manager) since it's request-scoped, one dict per
    # running batch, mirroring _progress_cb's own closure just above.
    trade_stats = {"total_trades": 0, "wins": 0, "cumulative_pnl": 0.0, "peak_pnl": 0.0,
                   "max_drawdown": 0.0, "equity_curve": []}

    def _trade_cb(symbol, timeframe, trade):
        trade_stats["total_trades"] += 1
        if trade["pnl"] > 0:
            trade_stats["wins"] += 1
        trade_stats["cumulative_pnl"] += trade["pnl"]
        trade_stats["peak_pnl"] = max(trade_stats["peak_pnl"], trade_stats["cumulative_pnl"])
        trade_stats["max_drawdown"] = max(trade_stats["max_drawdown"],
                                           trade_stats["peak_pnl"] - trade_stats["cumulative_pnl"])
        trade_stats["equity_curve"].append(round(trade_stats["cumulative_pnl"], 4))
        if len(trade_stats["equity_curve"]) > 500:  # cap -- this is a live progress sparkline,
            trade_stats["equity_curve"] = trade_stats["equity_curve"][-500:]  # not the final report

        job_manager.update_progress(
            job_id,
            last_trade={
                "symbol": symbol, "timeframe": timeframe, "side": trade["side"],
                "pnl": trade["pnl"], "trade_num": trade["trade_num"],
                "entry_reason": trade.get("entry_reason"), "exit_reason": trade.get("exit_reason"),
            },
            total_trades=trade_stats["total_trades"], wins=trade_stats["wins"],
            cumulative_pnl=round(trade_stats["cumulative_pnl"], 4),
            max_drawdown=round(trade_stats["max_drawdown"], 4),
            equity_curve=trade_stats["equity_curve"],
        )

    log_fn = job_manager.make_log_fn(job_id)

    def _target():
        batch_id = runner.run_mtf_batch(
            cfg, exchange, symbols, settings,
            start_ms=settings["start_ms"], end_ms=settings["end_ms"],
            log=log_fn, control=control, progress_cb=_progress_cb, trade_cb=_trade_cb,
            use_multiprocessing=req.use_multiprocessing,
            extraction_override_warning=extraction_override_warning,
        )
        generate_report(batch_id)
        return {"batch_id": batch_id}

    job_manager.create_job("backtest", _target, control=control, job_id=job_id)
    sync.notify("backtest", "started", f"Backtesting started: {cfg.name}", job_id=job_id)
    return {"job_id": job_id}
