from fastapi import APIRouter
from pydantic import BaseModel

from ai_integration import web_research

router = APIRouter()


class ResearchQuery(BaseModel):
    query: str
    max_results: int = 5


@router.post("/api/research/search")
def search_and_queue(req: ResearchQuery):
    """Autonomous Strategy Research (item 9) -- ON-DEMAND ONLY, this is the
    one and only trigger; nothing calls this on a schedule. Every result is
    queued through the exact same pipeline a manually pasted strategy uses
    (no auto-approve, no auto-deploy)."""
    return web_research.research_and_queue(req.query, max_results=req.max_results)


class ResearchUrl(BaseModel):
    url: str
    title: str | None = None


@router.post("/api/research/queue-url")
def queue_url(req: ResearchUrl):
    """Direct single-URL path -- for when a person already has a specific
    article link (from a trusted source) rather than a search query."""
    return web_research.queue_from_url(req.url, title=req.title)


@router.get("/api/research/trusted-sources")
def get_trusted_sources():
    return {"domains": sorted(web_research.TRUSTED_DOMAINS)}
