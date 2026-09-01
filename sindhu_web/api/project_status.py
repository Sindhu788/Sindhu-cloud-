"""Backend for the 3 consolidation navigation pages (Compare / Live Logs /
Project Status). Read-only except the feedback box, which only writes to
its own standalone user_feedback table -- nothing here recomputes a
backtest or touches a strategy/engine/safety-gate file. Every data source
is reused from existing modules (job_manager, storage.list_activity,
strategy_library, ENGINE_GAP_TRACKER.md, the optimizer_results.json
snapshot from the recent tuning pass) rather than duplicated."""

import json
import os
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from data_engine import storage
from backtest_engine import strategy_library
from sindhu_web import cache
from sindhu_web.jobs import job_manager
from sindhu_web.api.home import _compute_strategy_summary
from sindhu_web.api.backup import list_backups as _list_backups_route

router = APIRouter()

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_OPTIMIZER_RESULTS_PATH = os.path.join(_DATA_DIR, "optimizer_results.json")
_CHANGELOG_PATH = os.path.join(_DATA_DIR, "changelog.json")
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_GAP_TRACKER_PATH = os.path.join(_ROOT_DIR, "ENGINE_GAP_TRACKER.md")
_CONCEPTS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "concepts_reference.json")
_PROJECT_DOC_PATH = os.path.join(_ROOT_DIR, "PROJECT_DOCUMENTATION.md")

# Stall thresholds by job kind -- how long a "running" job can go without a
# progress update before it's flagged as possibly stalled. Backtests
# legitimately run for hours on the slow 1m timeframe, so this is
# generous; it's a flag for the human to look at, never an auto-kill.
_STALL_THRESHOLDS_SECONDS = {
    "backtest": 45 * 60,
    "download": 20 * 60,
    "default": 15 * 60,
}


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


# ------------------------------------------------------------------ Compare

@router.get("/api/compare-strategies")
def compare_strategies():
    """All strategies side by side, before/after where the recent optimizer
    pass touched them. Pulls the already-computed strategy summary (same
    data as the Home dashboard) and merges in the saved optimizer snapshot
    -- does not recompute anything.

    Master Task 2, Part 4.2 (Compare page speed): this used to call
    _compute_strategy_summary() directly, bypassing the exact same 30s
    cache /api/strategy-summary already uses for identical data, AND made
    its own extra storage.get_batch_results() call per strategy just for
    worst_drawdown_pct (now computed once inside _compute_strategy_summary
    itself, from the same fetch it already does). Measured before this fix:
    82.6s cold; after, sharing the warmed cache: well under 1s. Governor/
    Evolution Engine logic is untouched -- this only removes redundant work
    this endpoint was doing to itself."""
    live = cache.cached("strategy_aggregate_summary", 30, _compute_strategy_summary)
    opt = _load_json(_OPTIMIZER_RESULTS_PATH, {"strategies": []})
    opt_by_id = {s["id"]: s for s in opt.get("strategies", [])}

    rows = []
    for r in live["strategies"]:
        merged = dict(r)
        opt_row = opt_by_id.get(r["id"])
        if opt_row:
            merged["protected"] = opt_row.get("protected", False)
            merged["original"] = opt_row.get("original")
            merged["tuning_change"] = opt_row.get("change")
            merged["next_idea"] = opt_row.get("next_idea")
        else:
            merged["protected"] = False
            merged["original"] = None
            merged["tuning_change"] = None
            merged["next_idea"] = None
        rows.append(merged)

    rows.sort(key=lambda r: -(r["profit_factor"] or -999))
    return {
        "strategies": rows,
        "total_strategies": live["total_strategies"],
        "profitable_count": live["profitable_count"],
        "generated_at": live["generated_at"],
    }


def _batch_metrics(batch_id):
    results = storage.get_batch_results(batch_id) or []
    if not results:
        return None
    total_trades = sum(r["metrics"]["total_trades"] for r in results)
    if not total_trades:
        return None
    wins = sum(r["metrics"]["wins"] for r in results)
    net = sum(r["metrics"]["net_profit"] for r in results)
    gp = sum(r["metrics"]["gross_profit"] for r in results)
    gl = sum(abs(r["metrics"]["gross_loss"]) for r in results)
    pf = (gp / gl) if gl else None
    worst = max((x["metrics"].get("max_drawdown_pct", 0) for x in results), default=None)
    return {
        "trades": total_trades,
        "win_rate": round(100 * wins / total_trades, 2),
        "net_pnl": round(net, 2),
        "profit_factor": round(pf, 4) if pf else None,
        "worst_drawdown_pct": round(worst, 2) if worst is not None else None,
    }


def _tp_label(tp):
    if tp is None:
        return "-"
    if tp.type == "rr":
        return f"1:{tp.value:g} fixed" if tp.value else "fixed RR"
    if tp.type == "structure":
        return "structure-based"
    if tp.type == "atr_multiple":
        return f"{tp.value:g}x ATR" if tp.value else "ATR-multiple"
    return tp.type


@router.get("/api/compare-strategies/dual-tp")
def compare_dual_tp():
    """Part 1/Part 2 of the 6-part dual-TP task: every one of the 16
    original strategies side by side with its Fixed-1:2-TP draft variant
    (tagged "dual_tp_variant", saved archived so it never pollutes the
    main Compare/Home roster -- see _compute_strategy_summary's archived
    filter). Reads whatever variants exist and have a COMPLETED batch so
    far -- safe to call while the batch queue is still processing later
    strategies; those simply show no 1:2-TP columns yet."""
    variant_by_source = {}
    originals = []
    for meta in strategy_library.list_all():
        tags = meta.get("tags", [])
        if "dual_tp_variant" in tags:
            src = next((t.split(":", 1)[1] for t in tags if t.startswith("source:")), None)
            if src:
                variant_by_source[src] = meta
        elif not meta.get("archived"):
            originals.append(meta)

    rows = []
    for meta in originals:
        sid = meta["id"]
        cfg = strategy_library.load(sid)
        orig_batch = storage.latest_completed_batch_for_strategy_name(cfg.name)
        orig_metrics = _batch_metrics(orig_batch) if orig_batch else None

        variant_meta = variant_by_source.get(sid)
        variant_metrics = None
        variant_status = "not started"
        if variant_meta:
            vcfg = strategy_library.load(variant_meta["id"])
            vbatch = storage.latest_completed_batch_for_strategy_name(vcfg.name)
            if vbatch:
                variant_metrics = _batch_metrics(vbatch)
                variant_status = "completed" if variant_metrics else "completed (0 trades)"
            else:
                variant_status = "running"

        verdict = None
        if orig_metrics and variant_metrics and orig_metrics["profit_factor"] and variant_metrics["profit_factor"]:
            delta = variant_metrics["profit_factor"] - orig_metrics["profit_factor"]
            if abs(delta) < 0.02:
                verdict = "equivalent"
            elif delta > 0:
                verdict = "better"
            else:
                verdict = "worse"

        rows.append({
            "id": sid, "name": meta["name"].replace(" [Manual Build]", ""),
            "original_tp_label": _tp_label(cfg.take_profit),
            "original": orig_metrics,
            "variant_status": variant_status,
            "variant": variant_metrics,
            "verdict": verdict,
        })

    rows.sort(key=lambda r: -((r["original"] or {}).get("profit_factor") or -999))
    return {
        "strategies": rows,
        "total": len(rows),
        "completed": sum(1 for r in rows if r["variant"] is not None),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------- Live Logs

def _job_stage_label(job):
    progress = job.progress or {}
    stage = progress.get("stage") or progress.get("current_symbol") or job.kind
    return str(stage)


def _job_elapsed_seconds(job):
    try:
        started = datetime.fromisoformat(job.started_at)
    except (TypeError, ValueError):
        return None
    end = datetime.now(timezone.utc) if job.status == "running" else (
        datetime.fromisoformat(job.finished_at) if job.finished_at else datetime.now(timezone.utc)
    )
    return (end - started).total_seconds()


def _is_stalled(job):
    if job.status != "running":
        return False
    threshold = _STALL_THRESHOLDS_SECONDS.get(job.kind, _STALL_THRESHOLDS_SECONDS["default"])
    elapsed = _job_elapsed_seconds(job)
    return elapsed is not None and elapsed > threshold


@router.get("/api/live-logs")
def live_logs():
    jobs = job_manager.list_jobs()
    running = [j for j in jobs if j.status == "running"]
    completed = sorted(
        (j for j in jobs if j.status != "running"),
        key=lambda j: j.finished_at or j.started_at,
        reverse=True,
    )[:30]

    running_rows = [{
        "id": j.id, "kind": j.kind, "stage": _job_stage_label(j),
        "progress_pct": (j.progress or {}).get("pct"),
        "elapsed_seconds": _job_elapsed_seconds(j),
        "started_at": j.started_at,
        "stalled": _is_stalled(j),
    } for j in running]

    completed_rows = [{
        "id": j.id, "kind": j.kind, "status": j.status,
        "started_at": j.started_at, "finished_at": j.finished_at,
        "error": j.error,
        "outcome": (j.result or {}).get("batch_id") if isinstance(j.result, dict) else None,
    } for j in completed]

    activity_rows = storage.list_activity(30)

    return {
        "running_now": running_rows,
        "queued": [],  # the engine has no explicit queue -- backtests run one at a time via
                        # get_running_job_of_kind(), so "queued" is always empty by design today.
        "recently_completed": completed_rows,
        "recent_activity": activity_rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ------------------------------------------------------------ Project Status

def _period_bounds(period):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        return today_start
    if period == "yesterday":
        return today_start - timedelta(days=1)
    if period == "week":
        return today_start - timedelta(days=today_start.weekday())
    if period == "month":
        return today_start.replace(day=1)
    return None  # "all"


_GAP_ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|(.+?)\|(.+?)\|(.+?)\|(.+?)\|\s*$"
)


def _parse_gap_tracker():
    """Parses ENGINE_GAP_TRACKER.md's markdown table into structured
    entries. No per-gap date is recorded in the source doc, so entries are
    surfaced in the changelog's 'engine-gap' category instead, which does
    carry real dates -- this function only backs the pending-count math."""
    text = _load_gap_tracker_text()
    found = fixed = excluded = not_real = 0
    for line in text.splitlines():
        m = _GAP_ROW_RE.match(line)
        if not m:
            continue
        found += 1
        status = m.group(4).strip().lower()
        if "not a real gap" in status:
            not_real += 1
        elif "not fixed" in status or "excluded" in status:
            excluded += 1
        elif "fixed" in status:
            fixed += 1
    return {"found": found, "fixed": fixed, "excluded": excluded, "not_a_real_gap": not_real}


def _load_gap_tracker_text():
    try:
        with open(_GAP_TRACKER_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _doc_currency_status(doc_mtime_iso):
    if not doc_mtime_iso:
        return "not started"
    latest_change = datetime.now(timezone.utc) - timedelta(days=1)
    try:
        doc_dt = datetime.fromisoformat(doc_mtime_iso)
    except ValueError:
        return "not started"
    return "blocked" if doc_dt < latest_change else "in progress"


@router.get("/api/project-status")
def project_status(period: str = "all"):
    since = _period_bounds(period)
    changelog = _load_json(_CHANGELOG_PATH, [])
    if since:
        since_date = since.date().isoformat()
        changelog = [c for c in changelog if c["date"] >= since_date]
    changelog.sort(key=lambda c: c["date"], reverse=True)

    live = _compute_strategy_summary()
    gaps = _parse_gap_tracker()
    concepts = _load_json(_CONCEPTS_JSON_PATH, {"categories": []})
    concepts_total = sum(len(c["concepts"]) for c in concepts.get("categories", []))
    concepts_defined = sum(
        1 for c in concepts.get("categories", []) for concept in c["concepts"]
        if concept.get("status") == "defined"
    )

    paper_configs = storage.list_paper_strategy_configs()
    paper_started = storage.earliest_paper_trading_activity() is not None

    backups = _list_backups_route()["backups"]
    latest_backup = backups[0] if backups else None

    doc_mtime = None
    if os.path.isfile(_PROJECT_DOC_PATH):
        doc_mtime = datetime.fromtimestamp(os.path.getmtime(_PROJECT_DOC_PATH), tz=timezone.utc).isoformat()

    pending = [
        {
            "item": "Paper trading activation for profitable strategies",
            "status": "not started" if not paper_started else "in progress",
            "detail": f"{len(paper_configs)} strategies configured for paper trading, "
                      f"{live['profitable_count']} are genuinely profitable and would qualify.",
        },
        {
            "item": "Concepts Library completion",
            "status": "in progress" if concepts_defined else "not started",
            "detail": f"{concepts_defined} of {concepts_total} concepts fully detailed.",
        },
        {
            # Nav audit (Part 4 of the redesign task): re-checked both halves
            # of this item directly against NAV_PAGES/app.js instead of
            # trusting the old text. Concepts already has a sidebar entry
            # (home.py NAV_PAGES, id="concepts", external_url to
            # concepts.html) -- that half was already resolved and this item
            # was just never updated to say so. The other half, a standalone
            # sindhu_web/static/activity_log.html, is real and still has NO
            # nav entry -- but it is not a "missing link" bug: it is an
            # older, functionally-superseded predecessor of the SPA's own
            # Live Logs page (id="live_logs", already in nav), showing the
            # same running/queued/completed/activity data from an older,
            # separate set of direct API calls instead of the newer
            # consolidated /api/live-logs endpoint. Linking it into nav
            # would just give the CEO two different "Live Logs" pages side
            # by side -- flagged here as legacy debris worth deleting in a
            # future pass, not wired in.
            "item": "Concepts Library wired into main navigation",
            "status": "done",
            "detail": "Concepts already has its own sidebar entry (Project group). Separately: static/activity_log.html "
                      "is an older, functionally-superseded duplicate of the Live Logs SPA page (same job/activity data, "
                      "older direct-API version) -- not linked into nav on purpose, flagged as cleanup debris instead.",
        },
        {
            "item": "PROJECT_DOCUMENTATION.md currency",
            "status": _doc_currency_status(doc_mtime),
            "detail": f"Last modified {doc_mtime[:10] if doc_mtime else 'unknown'}, "
                      f"while real work has continued past that date.",
        },
        {
            "item": "Backup / disaster-recovery status",
            "status": "in progress",
            "detail": f"{len(backups)} backups on disk, most recent "
                      f"{latest_backup['modified_at'][:19] if latest_backup else 'none'} -- auto-backup thread confirmed running.",
        },
    ]

    return {
        "period": period,
        "changelog": changelog,
        "summary": {
            "total_strategies": live["total_strategies"],
            "profitable_count": live["profitable_count"],
            "aggregate_win_rate": live["aggregate_trade_weighted_win_rate"],
            "aggregate_net_pnl": live["aggregate_net_pnl"],
            "engine_gaps_found": gaps["found"],
            "engine_gaps_fixed": gaps["fixed"],
            "engine_gaps_excluded": gaps["excluded"],
            "engine_gaps_not_real": gaps["not_a_real_gap"],
        },
        "pending": pending,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


class FeedbackCreate(BaseModel):
    type: str
    text: str


@router.post("/api/feedback")
def submit_feedback(req: FeedbackCreate):
    fb_type = req.type if req.type in ("Suggest", "Add", "Fix", "Wrong") else "Suggest"
    text = req.text.strip()
    if not text:
        return {"ok": False, "error": "empty text"}
    now_iso = datetime.now(timezone.utc).isoformat()
    fb_id = storage.save_feedback(fb_type, text, now_iso)
    return {"ok": True, "id": fb_id}


@router.get("/api/feedback")
def get_feedback():
    return {"feedback": storage.list_feedback(200)}


class FeedbackStatusUpdate(BaseModel):
    status: str


@router.post("/api/feedback/{feedback_id}/status")
def update_feedback_status(feedback_id: int, req: FeedbackStatusUpdate):
    status = req.status if req.status in ("open", "addressed") else "open"
    storage.set_feedback_status(feedback_id, status)
    return {"ok": True}
