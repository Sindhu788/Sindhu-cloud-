from fastapi import APIRouter
from pydantic import BaseModel

from sindhu_web import manager_chat

router = APIRouter()


class AskRequest(BaseModel):
    question: str
    lang: str = "ur"


@router.post("/api/manager-chat/ask")
def ask(req: AskRequest):
    return manager_chat.ask(req.question, lang=req.lang if req.lang in ("ur", "en") else "ur")
