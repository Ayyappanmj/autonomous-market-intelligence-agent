"""FastAPI application factory."""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.agents.llm import LLMClient, build_llm_client
from app.api.ratelimit import RateLimiter
from app.api.routes import router
from app.config import Settings, get_settings
from app.ingestion.rss_reader import FeedFetcher
from app.storage.repository import Repository, SQLiteRepository
from app.utils.logging import configure_logging, get_logger
from app.workflows.briefing_workflow import BriefingWorkflow

log = get_logger(__name__)


def create_app(settings: Optional[Settings] = None, repo: Optional[Repository] = None,
               fetcher: Optional[FeedFetcher] = None, llm: Optional[LLMClient] = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    repo = repo or SQLiteRepository(settings.database_path)
    repo.init()
    fetcher = fetcher or FeedFetcher(settings)
    llm = llm if llm is not None else build_llm_client(settings)

    app = FastAPI(title=settings.app_name, version=settings.version,
                  description="Source-grounded multi-agent market news briefings. Not investment advice.")
    app.state.settings = settings
    app.state.repo = repo
    app.state.limiter = RateLimiter()
    app.state.workflow = BriefingWorkflow(settings, repo, fetcher, llm)

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.max_request_bytes:
            return JSONResponse({"detail": "Request body too large."}, status_code=413)
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        fields = [".".join(str(p) for p in e.get("loc", [])[1:]) or "body" for e in exc.errors()]
        return JSONResponse({"detail": "Invalid request.", "fields": fields}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.error("unhandled error", extra={"path": request.url.path, "error_type": type(exc).__name__})
        return JSONResponse({"detail": "Internal server error."}, status_code=500)

    app.include_router(router)
    return app


# Run with:  uvicorn app.main:create_app --factory
