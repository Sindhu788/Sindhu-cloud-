from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai_integration import web_research
from backtest_engine import strategy_library as lib
from data_engine import storage, config as base_config

router = APIRouter()

_SETTINGS_FILE = "research_settings.json"
_DEFAULT_SETTINGS = {
    # Autonomous Strategy Research makes real outbound web requests and
    # (for anything that gets queued) uses an AI import call -- this cap
    # exists to respect API/usage limits, same purpose as Telegram's own
    # rate_limit_per_hour. A "run" is one search or one single-URL queue,
    # counted in research_run_log regardless of how many articles it
    # actually queued.
    "max_runs_per_day": 1,
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_settings():
    return base_config.load_or_seed(_SETTINGS_FILE, _DEFAULT_SETTINGS)


def _runs_today():
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    return storage.count_research_runs_since(since)


def _check_rate_limit():
    settings = load_settings()
    limit = settings.get("max_runs_per_day", 1)
    used = _runs_today()
    if used >= limit:
        raise HTTPException(
            429,
            f"Autonomous research is limited to {limit} run(s) per day "
            f"(already used {used}/{limit} in the last 24 hours). "
            f"Change this in Settings if you need more.",
        )


class ResearchQuery(BaseModel):
    query: str
    max_results: int = 5


@router.post("/api/research/search")
def search_and_queue(req: ResearchQuery):
    """Autonomous Strategy Research (item 9) -- ON-DEMAND ONLY, this is the
    one and only trigger; nothing calls this on a schedule. Every result is
    queued through the exact same pipeline a manually pasted strategy uses
    (no auto-approve, no auto-deploy). Gated by the configurable daily
    rate limit (see /api/research/settings) before it makes any real web
    request."""
    _check_rate_limit()
    result = web_research.research_and_queue(req.query, max_results=req.max_results)
    storage.log_research_run("search", req.query, len(result.get("queued") or []), _now_iso())
    return result


class ResearchUrl(BaseModel):
    url: str
    title: Optional[str] = None


@router.post("/api/research/queue-url")
def queue_url(req: ResearchUrl):
    """Direct single-URL path -- for when a person already has a specific
    article link (from a trusted source) rather than a search query. Same
    rate limit as a search (a "run" either way)."""
    _check_rate_limit()
    result = web_research.queue_from_url(req.url, title=req.title)
    storage.log_research_run("queue_url", req.url, 1 if result.get("queued") else 0, _now_iso())
    return result


@router.get("/api/research/trusted-sources")
def get_trusted_sources():
    return {"domains": sorted(web_research.TRUSTED_DOMAINS)}


@router.get("/api/research/settings")
def get_settings():
    settings = load_settings()
    return {**settings, "runs_used_today": _runs_today()}


class SettingsUpdate(BaseModel):
    max_runs_per_day: Optional[int] = None


@router.post("/api/research/settings")
def update_settings(req: SettingsUpdate):
    settings = load_settings()
    if req.max_runs_per_day is not None:
        if req.max_runs_per_day < 1:
            raise HTTPException(400, "max_runs_per_day must be at least 1")
        settings["max_runs_per_day"] = req.max_runs_per_day
    base_config.save_config(_SETTINGS_FILE, settings)
    return settings


@router.get("/api/research/runs")
def get_runs(limit: int = 20):
    return {"runs": storage.list_research_runs(limit=limit), "runs_used_today": _runs_today(),
            "settings": load_settings()}


@router.get("/api/research/web-sourced-strategies")
def get_web_sourced_strategies():
    """Dedicated "Web-Sourced Strategies" listing (Part 3, item 1): every
    strategy that was actually produced from a web-research-queued
    document, tagged with its real source URL/domain -- separate from
    manually-pasted strategies, which never carry a URL-shaped
    source_type (see knowledge_compiler.normalizer.detect_source_type:
    only a real source_hint URL, passed only by web_research.py, ever
    ends up here). No new storage tables needed -- purely a read-time
    join over compiled_documents + strategy_library, which every
    web-sourced strategy already already goes through unmodified (same
    validation/safety pipeline as any manual import)."""
    docs = storage.list_compiled_documents(limit=1000)
    web_docs = [d for d in docs if (d.get("source_type") or "").startswith(("http://", "https://"))]

    metas_by_id = {m["id"]: m for m in lib.list_all()}
    strategies = []
    for doc in web_docs:
        for strategy_id in doc.get("strategy_ids") or []:
            meta = metas_by_id.get(strategy_id)
            if not meta:
                continue
            source_url = doc["source_type"]
            domain = source_url.split("/")[2] if "//" in source_url else source_url
            strategies.append({
                "strategy_id": strategy_id,
                "strategy_name": meta.get("name"),
                "safety_status": meta.get("safety_status"),
                "tags": meta.get("tags", []),
                "source": "Web Research",
                "source_url": source_url,
                "source_domain": domain,
                "document_title": doc.get("title"),
                "queued_at": doc.get("created_at"),
            })
    strategies.sort(key=lambda s: s.get("queued_at") or "", reverse=True)
    return {"strategies": strategies, "count": len(strategies)}
