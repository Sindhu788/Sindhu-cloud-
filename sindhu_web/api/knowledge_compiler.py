from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_engine import storage
from knowledge_compiler.compiler import compile_document
from sindhu_web import sync

router = APIRouter()


class CompileRequest(BaseModel):
    text: str
    title: Optional[str] = None
    source_hint: Optional[str] = None


@router.post("/api/knowledge-compiler/compile")
def compile_text(req: CompileRequest):
    if not req.text or not req.text.strip():
        raise HTTPException(400, "No text provided.")
    doc = compile_document(req.text, title=req.title, source_hint=req.source_hint)
    saved_strategies = sum(1 for s in doc.strategies if s.saved_strategy_id)
    saved_lessons = sum(1 for l in doc.lessons if l.saved)
    sync.notify(
        "knowledge_compiler", "compiled",
        f"Compiled '{doc.title}' -> {doc.doc_type} ({saved_strategies} strategies, {saved_lessons} lessons)",
        id=doc.id,
    )
    return doc.to_dict()


@router.get("/api/knowledge-compiler/documents")
def list_documents(doc_type: Optional[str] = None, status: Optional[str] = None, limit: int = 50):
    return {"documents": storage.list_compiled_documents(doc_type=doc_type, status=status, limit=limit)}


@router.get("/api/knowledge-compiler/documents/{doc_id}")
def get_document(doc_id: str):
    doc = storage.get_compiled_document(doc_id)
    if not doc:
        raise HTTPException(404, "compiled document not found")
    return doc


@router.get("/api/knowledge-compiler/concepts")
def list_concepts():
    return {"concepts": storage.list_knowledge_concepts()}
