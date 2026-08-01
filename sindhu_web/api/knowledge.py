from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_engine import storage
from knowledge_engine.lesson import new_lesson, from_storage_dict, CATEGORIES, now_iso
from knowledge_engine.scoring import compute_knowledge_score, list_lessons_with_stats
from knowledge_engine.engine import get_display_knowledge_report
from sindhu_web import sync, cache

router = APIRouter()


@router.get("/api/knowledge/categories")
def get_categories():
    return {"categories": CATEGORIES}


@router.get("/api/knowledge/report")
def get_report():
    # Shares the same "knowledge_report" cache entry as /api/home so this
    # expensive aggregation (COUNT/SUM over a lesson_applications table
    # that's grown into the millions of rows) only runs once per TTL
    # window no matter which page hits it first, with stale-while-revalidate
    # so neither page ever blocks on a slow recompute after the first one.
    cached_report = cache.cached("knowledge_report", 60, get_display_knowledge_report)
    report = dict(cached_report)
    report["knowledge_score"] = compute_knowledge_score(report)
    report["recent_lessons"] = storage.list_lessons()[:5]
    return report


@router.get("/api/knowledge/lessons")
def list_lessons(status: Optional[str] = None, category: Optional[str] = None, q: str = ""):
    lessons = list_lessons_with_stats(status=status, category=category)
    if q:
        q_lower = q.lower()
        lessons = [l for l in lessons if q_lower in l["title"].lower() or q_lower in (l.get("description") or "").lower()]
    return {"lessons": lessons}


@router.get("/api/knowledge/lessons/{lesson_id}")
def get_lesson(lesson_id: str):
    lesson = storage.get_lesson(lesson_id)
    if not lesson:
        raise HTTPException(404, "lesson not found")
    lesson["stats"] = storage.get_lesson_stats(lesson_id)
    return lesson


class LessonRequest(BaseModel):
    title: str
    category: str = "Other"
    description: str = ""
    priority: str = "Medium"
    notes: str = ""
    status: str = "active"
    apply_backtesting: bool = True
    apply_paper_trading: bool = True
    apply_evolution: bool = True


@router.post("/api/knowledge/lessons")
def create_lesson(req: LessonRequest):
    lesson = new_lesson(
        title=req.title, category=req.category, description=req.description,
        priority=req.priority, notes=req.notes, status=req.status,
        apply_backtesting=req.apply_backtesting, apply_paper_trading=req.apply_paper_trading,
        apply_evolution=req.apply_evolution,
    )
    storage.save_lesson(lesson.to_storage_dict())
    sync.notify("lesson", "created", f"Lesson added: {lesson.title}", id=lesson.id)
    return lesson.to_storage_dict()


@router.put("/api/knowledge/lessons/{lesson_id}")
def update_lesson(lesson_id: str, req: LessonRequest):
    existing = storage.get_lesson(lesson_id)
    if not existing:
        raise HTTPException(404, "lesson not found")

    updated = new_lesson(
        title=req.title, category=req.category, description=req.description,
        priority=req.priority, notes=req.notes, status=req.status,
        apply_backtesting=req.apply_backtesting, apply_paper_trading=req.apply_paper_trading,
        apply_evolution=req.apply_evolution,
    )
    updated.id = lesson_id
    updated.created_at = existing["created_at"]
    storage.save_lesson(updated.to_storage_dict())
    sync.notify("lesson", "updated", f"Lesson updated: {updated.title}", id=lesson_id)
    return updated.to_storage_dict()


@router.delete("/api/knowledge/lessons/{lesson_id}")
def delete_lesson(lesson_id: str):
    existing = storage.get_lesson(lesson_id)
    if not existing:
        raise HTTPException(404, "lesson not found")
    storage.delete_lesson(lesson_id)
    sync.notify("lesson", "deleted", f"Lesson deleted: {existing['title']}", id=lesson_id)
    return {"ok": True}


@router.post("/api/knowledge/lessons/{lesson_id}/duplicate")
def duplicate_lesson(lesson_id: str):
    existing = storage.get_lesson(lesson_id)
    if not existing:
        raise HTTPException(404, "lesson not found")
    lesson = from_storage_dict(existing)
    dup = new_lesson(
        title=f"{lesson.title} (copy)", category=lesson.category, description=lesson.description,
        priority=lesson.priority, notes=lesson.notes, status="disabled",
        apply_backtesting=lesson.apply_backtesting, apply_paper_trading=lesson.apply_paper_trading,
        apply_evolution=lesson.apply_evolution,
    )
    storage.save_lesson(dup.to_storage_dict())
    sync.notify("lesson", "created", f"Lesson duplicated: {dup.title}", id=dup.id)
    return dup.to_storage_dict()


class StatusRequest(BaseModel):
    status: str


@router.post("/api/knowledge/lessons/{lesson_id}/status")
def set_lesson_status(lesson_id: str, req: StatusRequest):
    existing = storage.get_lesson(lesson_id)
    if not existing:
        raise HTTPException(404, "lesson not found")
    if req.status not in ("active", "disabled", "draft"):
        raise HTTPException(400, "status must be active, disabled, or draft")
    existing["status"] = req.status
    existing["updated_at"] = now_iso()
    storage.save_lesson(existing)
    sync.notify("lesson", "updated", f"Lesson status changed: {existing['title']} -> {req.status}", id=lesson_id)
    return {"ok": True}
