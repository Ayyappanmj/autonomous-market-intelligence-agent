"""Sequential, observable workflow:
Research -> Deduplication -> Analysis -> Verification -> Briefing Generation -> Final Validation."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.agents.analysis_agent import AnalysisAgent
from app.agents.briefing_agent import BriefingAgent
from app.agents.llm import LLMClient
from app.agents.research_agent import ResearchAgent
from app.agents.verification_agent import VerificationAgent
from app.config import Settings, select_feeds
from app.ingestion.deduplicator import deduplicate_detailed
from app.ingestion.rss_reader import FeedFetcher
from app.schemas.briefing import Briefing, GenerateRequest, StageStatus, WorkflowStatus
from app.storage.repository import Repository
from app.utils.logging import get_logger

log = get_logger(__name__)
STAGES = ["research", "deduplication", "analysis", "verification", "briefing_generation", "final_validation"]
MAX_REVISIONS = 2


class WorkflowBusy(Exception):
    """A generation job is already running."""


class WorkflowError(Exception):
    """Workflow failed; message is safe to show to users."""


class BriefingWorkflow:
    def __init__(self, settings: Settings, repo: Repository, fetcher: FeedFetcher,
                 llm: Optional[LLMClient] = None):
        self.settings, self.repo, self.fetcher, self.llm = settings, repo, fetcher, llm
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    def run(self, req: GenerateRequest, now: Optional[datetime] = None,
            feeds: Optional[dict[str, str]] = None) -> Briefing:
        if not self._lock.acquire(blocking=False):
            raise WorkflowBusy("a briefing is already being generated")
        try:
            return self._run(req, now or datetime.now(timezone.utc), feeds)
        finally:
            self._lock.release()

    def _run(self, req: GenerateRequest, now: datetime, feeds: Optional[dict[str, str]]) -> Briefing:
        status = WorkflowStatus(run_id=uuid.uuid4().hex[:12], state="running", started_at=now,
                                stages=[StageStatus(name=n) for n in STAGES])
        stage = {s.name: s for s in status.stages}
        self.repo.save_status(status)

        def begin(name: str, detail: str = "") -> None:
            stage[name].state, stage[name].started_at, stage[name].detail = "running", datetime.now(timezone.utc), detail
            self.repo.save_status(status)

        def end(name: str, detail: str = "") -> None:
            stage[name].state, stage[name].finished_at = "completed", datetime.now(timezone.utc)
            if detail:
                stage[name].detail = detail
            self.repo.save_status(status)

        current = "research"
        try:
            llm = self.llm if req.use_llm else None
            status.mode = "llm" if llm else "deterministic_fallback"
            topics = [t for t in req.topics]

            begin("research")
            chosen = feeds or select_feeds(self.settings.feeds, self.settings.feed_topics, topics,
                                           self.settings.max_feeds_per_run)
            research = ResearchAgent(self.settings, self.fetcher).run(req.days, now, chosen)
            status.errors += research.errors
            if not research.articles:
                raise WorkflowError("No articles could be retrieved from the configured feeds.")
            end("research", f"{len(research.articles)} articles, {research.rejected} rejected, "
                            f"{len(research.errors)} feed error(s)")

            current = "deduplication"
            begin("deduplication")
            unique, groups = deduplicate_detailed(research.articles)
            end("deduplication", f"{len(unique)} unique, {sum(len(v) for v in groups.values())} duplicates removed")

            current = "analysis"
            begin("analysis")
            analysis = AnalysisAgent(self.settings, llm).run(unique, topics)
            if not analysis.articles:
                raise WorkflowError("No retrieved articles matched the selected topics.")
            if analysis.llm_error:
                status.errors.append(analysis.llm_error)
            end("analysis", f"{len(analysis.articles)} articles analysed, {len(analysis.themes)} themes")

            current = "verification"
            begin("verification")
            writer = BriefingAgent(llm)
            verifier = VerificationAgent(self.settings.stale_after_hours)
            corroboration = {a.id: groups.get(a.id, []) for a in analysis.articles}
            evidence = list(analysis.articles) + [d for a in analysis.articles for d in corroboration[a.id]]
            claims = writer.compose_claims(analysis.articles, corroboration)
            removed, result = 0, verifier.verify(claims, evidence, now)
            for rev in range(1, MAX_REVISIONS + 1):
                if all(c.status in ("supported", "stale", "missing_date") for c in result.checks):
                    break
                before = len(claims)
                claims = writer.revise(claims, result)
                removed += before - len(claims)
                result = verifier.verify(claims, evidence, now, revisions=rev)
            result.unsupported_removed = removed
            result.revisions = max(result.revisions, 1 if removed else 0)
            end("verification", f"passed={result.passed}, revisions={result.revisions}")

            current = "briefing_generation"
            begin("briefing_generation")
            cited = {u for c in claims for u in c.source_urls}
            sources = [a for a in evidence if a.url in cited]
            undated = sum(1 for a in analysis.articles if a.published_at is None)
            briefing = writer.write(
                claims=claims, sources=sources, analysis=analysis, topics=topics,
                start=research.period_start, end=research.period_end, now=now, validation=result,
                feed_errors=research.errors, undated=undated)
            end("briefing_generation", f"mode={briefing.mode}")

            current = "final_validation"
            begin("final_validation")
            problems = verifier.final_validate(briefing)
            if problems:
                briefing.validation.flags += [f"final validation: {p}" for p in problems]
                briefing.validation.passed = False
            end("final_validation", "ok" if not problems else f"{len(problems)} problem(s) flagged")

            status.mode, status.state = briefing.mode, "completed"
            status.briefing_id, status.finished_at = briefing.id, datetime.now(timezone.utc)
            self.repo.upsert_articles(analysis.articles)
            self.repo.save_briefing(briefing)
            self.repo.save_status(status)
            log.info("briefing generated", extra={"briefing_id": briefing.id, "mode": briefing.mode})
            return briefing
        except WorkflowError as exc:
            self._fail(status, stage[current], str(exc))
            raise
        except Exception as exc:
            log.exception("workflow failed", extra={"stage": current})
            self._fail(status, stage[current], "internal error")
            raise WorkflowError("Briefing generation failed unexpectedly.") from exc

    def _fail(self, status: WorkflowStatus, st: StageStatus, message: str) -> None:
        st.state, st.error, st.finished_at = "failed", message, datetime.now(timezone.utc)
        status.state, status.finished_at = "failed", datetime.now(timezone.utc)
        status.errors.append(message)
        self.repo.save_status(status)
