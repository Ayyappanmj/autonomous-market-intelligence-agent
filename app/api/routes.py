"""REST API routes (v1)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.ratelimit import client_ip
from app.schemas.briefing import (
    Analytics, ArticlePage, Briefing, GenerateRequest, TOPICS, WorkflowStatus,
)
from app.workflows.briefing_workflow import WorkflowBusy, WorkflowError

router = APIRouter()


def general_limit(request: Request) -> None:
    s = request.app.state
    s.limiter.check(client_ip(request), "general", s.settings.rate_limit_per_min)


def generate_limit(request: Request) -> None:
    s = request.app.state
    s.limiter.check(client_ip(request), "generate", s.settings.generate_rate_limit_per_min)


@router.get("/health", tags=["system"])
def health(request: Request) -> dict:
    s = request.app.state
    try:
        s.repo.latest_status()
        db = "ok"
    except Exception:
        db = "unavailable"
    out = {"status": "ok" if db == "ok" else "degraded", "version": s.settings.version,
           "database": db, "llm_configured": s.settings.llm_configured}
    if s.settings.llm_configured:
        out["llm_provider"], out["llm_model"] = s.settings.llm_provider, s.settings.llm_model
    return out


@router.get("/", tags=["system"])
def info(request: Request) -> dict:
    st = request.app.state.settings
    return {
        "name": st.app_name,
        "version": st.version,
        "description": "Multi-agent pipeline that turns public RSS news into a source-grounded daily "
                       "market briefing. Sentiment is an analytical signal, not investment advice.",
        "docs": "/docs",
        "topics": TOPICS,
    }


@router.post("/api/v1/briefings/generate", response_model=Briefing, tags=["briefings"],
             dependencies=[Depends(generate_limit)])
def generate(req: GenerateRequest, request: Request) -> Briefing:
    wf = request.app.state.workflow
    try:
        return wf.run(req)
    except WorkflowBusy:
        raise HTTPException(status_code=409, detail="A briefing is already being generated.")
    except WorkflowError as exc:
        code = 503 if "No articles" in str(exc) or "matched" in str(exc) else 500
        raise HTTPException(status_code=code, detail=str(exc))


@router.get("/api/v1/briefings/latest", response_model=Briefing, tags=["briefings"],
            dependencies=[Depends(general_limit)])
def latest(request: Request) -> Briefing:
    b = request.app.state.repo.latest_briefing()
    if not b:
        raise HTTPException(status_code=404, detail="No briefing has been generated yet.")
    return b


@router.get("/api/v1/briefings/history", tags=["briefings"], dependencies=[Depends(general_limit)])
def history(request: Request, limit: int = Query(20, ge=1, le=50)) -> dict:
    return {"items": request.app.state.repo.list_briefings(limit)}


@router.get("/api/v1/briefings/{briefing_id}", response_model=Briefing, tags=["briefings"],
            dependencies=[Depends(general_limit)])
def get_briefing(briefing_id: str, request: Request) -> Briefing:
    if not briefing_id.isalnum() or len(briefing_id) > 32:
        raise HTTPException(status_code=422, detail="Invalid briefing id.")
    b = request.app.state.repo.get_briefing(briefing_id)
    if not b:
        raise HTTPException(status_code=404, detail="Briefing not found.")
    return b


@router.get("/api/v1/news", response_model=ArticlePage, tags=["news"], dependencies=[Depends(general_limit)])
def news(request: Request, topic: Optional[list[str]] = Query(None),
         page: int = Query(1, ge=1, le=1000), page_size: int = Query(20, ge=1, le=100)) -> ArticlePage:
    if topic and any(t not in TOPICS for t in topic):
        raise HTTPException(status_code=422, detail=f"topic must be one of {TOPICS}")
    return request.app.state.repo.list_articles(topic, page, page_size)


@router.get("/api/v1/analytics", response_model=Analytics, tags=["analytics"],
            dependencies=[Depends(general_limit)])
def analytics(request: Request) -> Analytics:
    return request.app.state.repo.analytics()


@router.get("/api/v1/feeds", tags=["news"], dependencies=[Depends(general_limit)])
def feeds(request: Request) -> dict:
    st = request.app.state.settings
    return {"items": [{"name": n, "url": u, "topics": list(st.feed_topics.get(n, ()))}
                      for n, u in st.feeds.items()],
            "max_feeds_per_run": st.max_feeds_per_run}


@router.get("/api/v1/agents/status", response_model=WorkflowStatus, tags=["agents"],
            dependencies=[Depends(general_limit)])
def agents_status(request: Request) -> WorkflowStatus:
    st = request.app.state.repo.latest_status()
    if st:
        if request.app.state.workflow.busy and st.state != "running":
            st = st.model_copy(update={"state": "running"})
        return st
    return WorkflowStatus(run_id="none", state="idle")
