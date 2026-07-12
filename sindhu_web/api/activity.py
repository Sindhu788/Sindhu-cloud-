from fastapi import APIRouter

from data_engine import storage

router = APIRouter()


@router.get("/api/activity")
def get_activity(limit: int = 50):
    return {"activity": storage.list_activity(limit)}
