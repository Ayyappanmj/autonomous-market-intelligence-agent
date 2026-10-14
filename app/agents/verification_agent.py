"""Agent 3 - Verification and Quality Control Agent (deterministic, source-grounded)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.schemas.briefing import Article, Briefing, Claim, ClaimCheck, ValidationResult

_WORD = re.compile(r"[a-z0-9]{3,}")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


class VerificationAgent:
    name = "Verification and Quality Control Agent"

    def __init__(self, stale_after_hours: int = 72, min_overlap: float = 0.6):
        self.stale_after = timedelta(hours=stale_after_hours)
        self.min_overlap = min_overlap

    def verify(self, claims: list[Claim], articles: list[Article], now: datetime,
               revisions: int = 0) -> ValidationResult:
        by_url = {a.url: a for a in articles}
        checks: list[ClaimCheck] = []
        flags: list[str] = []
        for claim in claims:
            cited = [by_url[u] for u in claim.source_urls if u in by_url]
            urls = [a.url for a in cited]
            if not cited:
                checks.append(ClaimCheck(claim=claim.text, status="unsupported",
                                         detail="no cited source found in retrieved articles", source_urls=[]))
                continue
            if claim.kind != "analytical_interpretation":
                source_text = " ".join(f"{a.title} {a.summary}" for a in cited)
                ct = _tokens(claim.text)
                if ct and len(ct & _tokens(source_text)) / len(ct) < self.min_overlap:
                    checks.append(ClaimCheck(claim=claim.text, status="unsupported",
                                             detail="claim wording is not found in the cited sources",
                                             source_urls=urls))
                    continue
            publishers = {a.publisher for a in cited}
            if claim.kind == "verified_fact" and len(publishers) < 2:
                checks.append(ClaimCheck(claim=claim.text, status="single_source",
                                         detail="only one publisher; cannot be called corroborated",
                                         source_urls=urls))
                continue
            dated = [a.published_at for a in cited if a.published_at]
            if not dated:
                checks.append(ClaimCheck(claim=claim.text, status="missing_date",
                                         detail="cited source has no publication date", source_urls=urls))
                flags.append(f"missing publication date: {claim.text[:70]}")
                continue
            if all(now - d > self.stale_after for d in dated):
                checks.append(ClaimCheck(claim=claim.text, status="stale",
                                         detail="cited sources are older than the staleness window",
                                         source_urls=urls))
                flags.append(f"stale source: {claim.text[:70]}")
                continue
            detail = (f"corroborated by {len(publishers)} publishers" if len(publishers) > 1
                      else "attributed to a single publisher (uncorroborated)")
            checks.append(ClaimCheck(claim=claim.text, status="supported", detail=detail, source_urls=urls))
        bad = {c.claim for c in checks if c.status in ("unsupported", "single_source")}
        important_bad = [c for c in claims if c.text in bad and c.important]
        return ValidationResult(passed=not important_bad, checks=checks, flags=flags, revisions=revisions)

    @staticmethod
    def final_validate(briefing: Briefing) -> list[str]:
        """Structural checks on the finished briefing. Returns a list of problems (empty == ok)."""
        problems: list[str] = []
        if briefing.period_end <= briefing.period_start:
            problems.append("reporting period is invalid")
        if not briefing.executive_summary.strip():
            problems.append("executive summary is empty")
        known = {a.url for a in briefing.sources}
        for c in briefing.key_developments:
            if not c.source_urls or any(u not in known for u in c.source_urls):
                problems.append(f"claim lacks a valid source reference: {c.text[:60]}")
        if "not market forecasts" not in briefing.markdown:
            problems.append("sentiment disclaimer missing from markdown")
        if briefing.mode_label not in briefing.markdown:
            problems.append("mode label missing from markdown")
        return problems
