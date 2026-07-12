from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from data_engine import storage
from sindhu_web import cache, sync
from backtest_engine import strategy_library

from ai_integration import config as ai_config
from ai_integration import providers as ai_providers
from ai_integration import file_extractors
from ai_integration import import_queue
from ai_integration import youtube_import
from ai_integration.importer import import_document
from ai_integration.quality_score import compute_knowledge_score

router = APIRouter()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _provider_public_view(name, entry):
    return {
        "name": name,
        "enabled": entry.get("enabled", False),
        "model": entry.get("model"),
        "temperature": entry.get("temperature"),
        "max_tokens": entry.get("max_tokens"),
        "timeout": entry.get("timeout"),
        "retry_count": entry.get("retry_count"),
        "has_api_key": bool(entry.get("api_key")),
        "api_key_masked": ai_config.mask_key(entry.get("api_key", "")),
        "last_test_status": entry.get("last_test_status"),
        "last_test_message": entry.get("last_test_message"),
        "last_test_at": entry.get("last_test_at"),
        "daily_quota": entry.get("daily_quota"),
        "monthly_quota": entry.get("monthly_quota"),
        "cost_per_1k_input": entry.get("cost_per_1k_input"),
        "cost_per_1k_output": entry.get("cost_per_1k_output"),
    }


@router.get("/api/ai/providers")
def list_providers():
    settings = ai_config.load_settings()
    return {
        "active_provider": settings.get("active_provider"),
        "providers": [
            _provider_public_view(name, entry) for name, entry in settings["providers"].items()
        ],
    }


class ProviderConfigUpdate(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: Optional[int] = None
    retry_count: Optional[int] = None
    daily_quota: Optional[int] = None
    monthly_quota: Optional[int] = None
    cost_per_1k_input: Optional[float] = None
    cost_per_1k_output: Optional[float] = None


@router.post("/api/ai/providers/{name}/config")
def update_provider_config(name: str, req: ProviderConfigUpdate):
    if name not in ai_config.SUPPORTED_PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {name}")
    entry = ai_config.update_provider_settings(
        name, api_key=req.api_key, model=req.model, temperature=req.temperature,
        max_tokens=req.max_tokens, timeout=req.timeout, retry_count=req.retry_count,
        daily_quota=req.daily_quota, monthly_quota=req.monthly_quota,
        cost_per_1k_input=req.cost_per_1k_input, cost_per_1k_output=req.cost_per_1k_output,
    )
    sync.notify("ai_integration", "provider_updated", f"AI provider '{name}' settings updated")
    return _provider_public_view(name, entry)


@router.post("/api/ai/providers/{name}/enable")
def enable_provider(name: str):
    if name not in ai_config.SUPPORTED_PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {name}")
    entry = ai_config.set_enabled(name, True)
    sync.notify("ai_integration", "provider_enabled", f"AI provider '{name}' enabled")
    return _provider_public_view(name, entry)


@router.post("/api/ai/providers/{name}/disable")
def disable_provider(name: str):
    if name not in ai_config.SUPPORTED_PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {name}")
    entry = ai_config.set_enabled(name, False)
    sync.notify("ai_integration", "provider_disabled", f"AI provider '{name}' disabled")
    return _provider_public_view(name, entry)


@router.post("/api/ai/providers/{name}/activate")
def activate_provider(name: str):
    if name not in ai_config.SUPPORTED_PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {name}")
    ai_config.set_active_provider(name)
    sync.notify("ai_integration", "provider_activated", f"AI provider '{name}' set as active")
    return {"active_provider": name}


@router.post("/api/ai/providers/deactivate")
def deactivate_provider():
    ai_config.set_active_provider(None)
    sync.notify("ai_integration", "provider_deactivated", "AI assistance deactivated -- SINDHU running rule-based only")
    return {"active_provider": None}


@router.post("/api/ai/providers/{name}/test")
def test_provider(name: str):
    if name not in ai_config.SUPPORTED_PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {name}")
    settings = ai_config.get_provider_settings(name)
    if not settings.get("api_key"):
        ai_config.record_test_result(name, "error", "No API key configured.", _now_iso())
        return {"ok": False, "message": "No API key configured.", "latency_ms": 0}

    provider = ai_providers.get_provider(name, settings)
    ok, message, latency_ms = provider.test_connection()
    status = "ok" if ok else "error"
    ai_config.record_test_result(name, status, message, _now_iso())
    storage.save_ai_usage_log(
        name, settings.get("model"), "/ai/test", status, _now_iso(),
        latency_ms=latency_ms, error_message=None if ok else message,
    )
    sync.notify("ai_integration", "provider_tested", f"AI provider '{name}' test: {status}")
    return {"ok": ok, "message": message, "latency_ms": latency_ms}


class ImportTextRequest(BaseModel):
    text: str
    title: Optional[str] = None
    source_hint: Optional[str] = None
    use_ai: bool = True


@router.post("/api/ai/import")
def import_text(req: ImportTextRequest):
    if not req.text or not req.text.strip():
        raise HTTPException(400, "No text provided.")
    result = import_document(req.text, title=req.title, source_hint=req.source_hint, use_ai=req.use_ai)
    if result.get("error") and not result.get("document"):
        raise HTTPException(422, result["error"])
    doc = result["document"]
    saved_strategies = sum(1 for s in doc["strategies"] if s.get("saved_strategy_id"))
    saved_lessons = sum(1 for l in doc["lessons"] if l.get("saved"))
    sync.notify(
        "ai_integration", "imported",
        f"Imported '{doc['title']}' ({'AI-assisted' if result['ai_assisted'] else 'rule-based'}) "
        f"-> {saved_strategies} strategies, {saved_lessons} lessons",
        id=doc["id"],
    )
    return result


@router.post("/api/ai/import/upload")
async def import_file(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    use_ai: bool = Form(True),
):
    raw_bytes = await file.read()
    try:
        text = file_extractors.extract_text(file.filename, raw_bytes)
    except (ImportError, ValueError) as exc:
        raise HTTPException(422, str(exc))

    if not text or not text.strip():
        raise HTTPException(422, f"No extractable text found in '{file.filename}'.")

    result = import_document(text, title=title or file.filename, source_hint=file.filename, use_ai=use_ai)
    if result.get("error") and not result.get("document"):
        raise HTTPException(422, result["error"])
    doc = result["document"]
    sync.notify(
        "ai_integration", "imported",
        f"Imported '{doc['title']}' from {file.filename} ({'AI-assisted' if result['ai_assisted'] else 'rule-based'})",
        id=doc["id"],
    )
    return result


class ImportYoutubeRequest(BaseModel):
    url: str
    title: Optional[str] = None
    use_ai: bool = True


@router.post("/api/ai/import/youtube")
def import_youtube(req: ImportYoutubeRequest):
    if not req.url or not req.url.strip():
        raise HTTPException(400, "No YouTube URL provided.")
    result = import_document(req.url, title=req.title, use_ai=req.use_ai, input_kind="youtube")
    if result.get("error") and not result.get("document"):
        raise HTTPException(422, result["error"])
    doc = result["document"]
    saved_strategies = sum(1 for s in doc["strategies"] if s.get("saved_strategy_id"))
    saved_lessons = sum(1 for l in doc["lessons"] if l.get("saved"))
    sync.notify(
        "ai_integration", "imported",
        f"Imported '{doc['title']}' from YouTube ({'AI-assisted' if result['ai_assisted'] else 'rule-based'}) "
        f"-> {saved_strategies} strategies, {saved_lessons} lessons",
        id=doc["id"],
    )
    return result


def _day_start_iso():
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _month_start_iso():
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


@router.get("/api/ai/usage")
def get_usage():
    settings = ai_config.load_settings()
    summary = {row["provider"]: row for row in storage.ai_usage_summary()}
    today = storage.ai_usage_since(_day_start_iso())
    this_month = storage.ai_usage_since(_month_start_iso())

    enriched = []
    for name in ai_config.SUPPORTED_PROVIDERS:
        entry = settings["providers"][name]
        base = summary.get(name, {
            "total_calls": 0, "success_calls": 0, "failed_calls": 0,
            "tokens_in": 0, "tokens_out": 0, "avg_latency_ms": 0, "avg_tokens": 0, "last_used_at": None,
        })
        day = today.get(name, {"total_calls": 0, "tokens_in": 0, "tokens_out": 0})
        month = this_month.get(name, {"total_calls": 0, "tokens_in": 0, "tokens_out": 0})
        daily_quota = entry.get("daily_quota")
        monthly_quota = entry.get("monthly_quota")
        cost = (
            (base["tokens_in"] / 1000.0) * entry.get("cost_per_1k_input", 0.0)
            + (base["tokens_out"] / 1000.0) * entry.get("cost_per_1k_output", 0.0)
        )
        enriched.append({
            **base,
            "provider": name,
            "provider_status": "enabled" if entry.get("enabled") else "disabled",
            "daily_requests": day["total_calls"],
            "monthly_requests": month["total_calls"],
            "daily_quota": daily_quota,
            "monthly_quota": monthly_quota,
            "daily_remaining": None if daily_quota is None else max(0, daily_quota - day["total_calls"]),
            "monthly_remaining": None if monthly_quota is None else max(0, monthly_quota - month["total_calls"]),
            "estimated_cost": round(cost, 4),
        })
    return {"summary": enriched}


@router.get("/api/ai/logs")
def get_logs(provider: Optional[str] = None, limit: int = 100):
    return {"logs": storage.list_ai_usage_log(provider=provider, limit=limit)}


@router.post("/api/ai/cache/clear")
def clear_cache():
    cache.clear_all()
    sync.notify("ai_integration", "cache_cleared", "AI Integration Center cache cleared")
    return {"ok": True}


class QueueImportItem(BaseModel):
    text: str
    title: Optional[str] = None
    source_hint: Optional[str] = None
    use_ai: bool = True
    input_kind: str = "text"   # "text" or "youtube" (text field holds the URL)


class QueueImportBatchRequest(BaseModel):
    items: List[QueueImportItem]


@router.post("/api/ai/import/queue")
def enqueue_import(req: QueueImportBatchRequest):
    if not req.items:
        raise HTTPException(400, "No items provided.")
    ids = import_queue.enqueue_batch([
        {
            "raw_text": item.text, "title": item.title, "source_hint": item.source_hint,
            "use_ai": item.use_ai, "input_kind": item.input_kind,
        }
        for item in req.items
    ])
    sync.notify("ai_integration", "queued", f"Queued {len(ids)} document(s) for import")
    return {"queue_ids": ids}


@router.get("/api/ai/import/queue")
def list_queue(status: Optional[str] = None, limit: int = 100):
    return {"items": storage.list_ai_import_queue(status=status, limit=limit)}


@router.post("/api/ai/import/queue/{item_id}/retry")
def retry_queue_item(item_id: str):
    try:
        item = import_queue.retry(item_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    sync.notify("ai_integration", "queue_retry", f"Re-queued import item {item_id}")
    return item


@router.post("/api/ai/import/queue/retry-failed")
def retry_failed_imports():
    count = import_queue.retry_all_failed()
    sync.notify("ai_integration", "queue_retry_all", f"Re-queued {count} failed import(s)")
    return {"retried": count}


@router.get("/api/ai/knowledge-score/{doc_id}")
def get_knowledge_score(doc_id: str):
    doc = storage.get_compiled_document(doc_id)
    if not doc:
        raise HTTPException(404, "compiled document not found")
    return compute_knowledge_score(doc)


@router.get("/api/ai/dictionary")
def list_ai_dictionary():
    return {"entries": storage.list_ai_dictionary_entries()}


@router.get("/api/ai/dashboard")
def get_ai_dashboard():
    """CEO Dashboard stats: what the whole Knowledge Import Center has
    produced so far, plus how reliable imports have been."""
    concepts = storage.list_knowledge_concepts()
    pattern_count = sum(1 for c in concepts if c["category"] == "structure")
    indicator_count = sum(1 for c in concepts if c["category"] == "indicator")
    queue_stats = storage.ai_import_queue_stats()
    usage = storage.ai_usage_summary()

    recent_docs = storage.list_compiled_documents(limit=200)
    total_hidden_rules = sum(len(d.get("hidden_rules") or []) for d in recent_docs)

    return {
        "total_strategies": len(strategy_library.list_all()),
        "total_lessons": len(storage.list_lessons()),
        "dictionary_size": len(storage.list_ai_dictionary_entries()),
        "pattern_count": pattern_count,
        "indicator_count": indicator_count,
        "success_rate_pct": queue_stats["success_rate_pct"],
        "failed_imports": queue_stats["failed"],
        "pending_imports": queue_stats["pending"] + queue_stats["processing"],
        "completed_imports": queue_stats["completed"],
        "total_ai_calls": sum(u["total_calls"] for u in usage),
        "total_hidden_rules_detected": total_hidden_rules,
        "youtube_import_available": youtube_import.transcript_api_available(),
        "provider_status": [
            {"provider": p["name"], "enabled": p["enabled"], "status": p["last_test_status"]}
            for p in [_provider_public_view(n, e) for n, e in ai_config.load_settings()["providers"].items()]
        ],
    }
