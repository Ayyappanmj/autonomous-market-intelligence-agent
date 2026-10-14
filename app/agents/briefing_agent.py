"""Agent 4 - Briefing Writer Agent. Template-based by default; LLM adds an optional, guarded summary."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.agents.analysis_agent import AnalysisOutput
from app.agents.llm import LLMClient, LLMUnavailable, SYSTEM_PROMPT, output_is_grounded, wrap_untrusted
from app.schemas.briefing import (
    Article, Briefing, Claim, SENTIMENT_DISCLAIMER, ValidationResult,
)

FALLBACK_LABEL = "Deterministic fallback (no LLM): extractive summaries and template text"
LLM_LABEL = "LLM-assisted summary and theme notes; all facts remain source-attributed"

WHY = {
    "ai": "May signal shifting competitive or regulatory dynamics in AI; no market impact is asserted.",
    "technology": "May affect technology-sector narratives and supply-chain expectations; impact is uncertain.",
    "markets": "May influence investor sentiment; this briefing makes no price or return predictions.",
    "business": "May indicate corporate strategy or earnings trends worth monitoring; effects are uncertain.",
    "energy": "May bear on energy-cost and supply discussions; direction of any effect is not asserted.",
    "economy": "May inform views on growth, inflation or policy; it is not an economic forecast.",
}


def _fmt(dt: Optional[datetime]) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "date not provided"


class BriefingAgent:
    name = "Briefing Writer Agent"

    def __init__(self, llm: Optional[LLMClient] = None, max_developments: int = 8):
        self.llm = llm
        self.max_developments = max_developments

    # ---- drafting
    def compose_claims(self, articles: list[Article],
                       corroboration: dict[str, list[Article]]) -> list[Claim]:
        """One claim per leading story. Claim text is the publisher's headline (extractive)."""
        ranked = sorted(
            [a for a in articles if not a.suspicious],
            key=lambda a: (-(len({a.publisher} | {d.publisher for d in corroboration.get(a.id, [])})),
                           -(a.published_at.timestamp() if a.published_at else 0)),
        )
        claims: list[Claim] = []
        for art in ranked[: self.max_developments]:
            dups = [d for d in corroboration.get(art.id, []) if d.publisher != art.publisher]
            members = [art] + dups
            publishers = sorted({m.publisher for m in members})
            kind = "verified_fact" if len(publishers) >= 2 else "source_attributed"
            topic = art.topics[0] if art.topics else "business"
            claims.append(
                Claim(
                    text=art.title,
                    kind=kind,
                    source_urls=[m.url for m in members],
                    publishers=publishers,
                    why_it_matters=WHY.get(topic, WHY["business"]),
                    published_at=art.published_at,
                )
            )
        return claims

    @staticmethod
    def revise(claims: list[Claim], result: ValidationResult) -> list[Claim]:
        """Drop unsupported claims; downgrade single-source 'verified' claims."""
        status = {c.claim: c.status for c in result.checks}
        revised: list[Claim] = []
        for c in claims:
            s = status.get(c.text)
            if s == "unsupported":
                continue
            if s == "single_source":
                c = c.model_copy(update={"kind": "source_attributed"})
            revised.append(c)
        return revised

    # ---- writing
    def _executive_summary(self, articles: list[Article], analysis: AnalysisOutput,
                           start: datetime, end: datetime) -> tuple[str, bool]:
        publishers = len({a.publisher for a in articles})
        s = analysis.sentiment
        theme = f" The most recurring theme was \"{analysis.themes[0].name}\"." if analysis.themes else ""
        base = (
            f"Between {_fmt(start)} and {_fmt(end)}, {len(articles)} unique articles from {publishers} "
            f"publishers were reviewed. Headline tone measured by a rule-based baseline: {s.positive} positive, "
            f"{s.neutral} neutral, {s.negative} negative (mean score {s.mean_score:+.2f}).{theme}"
        )
        if not self.llm:
            return base, False
        lines = [f"[{a.publisher}] {a.title}" for a in articles if not a.suspicious][:25]
        user = ('Write a 2-sentence executive summary of the main subjects in these headlines. '
                'Return JSON: {"summary": "..."}.\n' + wrap_untrusted(lines))
        corpus = " ".join(lines)
        try:
            data = self.llm.complete_json(SYSTEM_PROMPT, user)
            text = str(data.get("summary", "")).strip()[:600]
            if text and output_is_grounded(text, corpus):
                return f"{base} AI-generated overview: {text}", True
        except LLMUnavailable:
            pass
        return base, False

    def write(self, *, claims: list[Claim], sources: list[Article], analysis: AnalysisOutput,
              topics: list[str], start: datetime, end: datetime, now: datetime,
              validation: ValidationResult, feed_errors: list[str], undated: int) -> Briefing:
        unique = analysis.articles
        summary, summary_llm = self._executive_summary(unique, analysis, start, end)
        used_llm = bool(analysis.llm_used or summary_llm)
        mode, label = ("llm", LLM_LABEL) if used_llm else ("deterministic_fallback", FALLBACK_LABEL)

        risks = [f"{a.publisher} reported a negative-toned story: {a.title} ({a.url})"
                 for a in sorted(unique, key=lambda x: x.sentiment_score or 0)[:3]
                 if (a.sentiment_score or 0) <= -0.1]
        uncertainties = [
            "Headline/summary sentiment is a coarse baseline and can misread context, sarcasm or quotes.",
            "Themes reflect recurring terms in this retrieval window only, not full market coverage.",
        ]
        if undated:
            uncertainties.append(f"{undated} article(s) lacked a publication date and were treated cautiously.")
        uncertainties += [f"Feed unavailable: {e}" for e in feed_errors]

        briefing = Briefing(
            id=uuid.uuid4().hex[:12], generated_at=now, period_start=start, period_end=end,
            topics=topics, mode=mode, mode_label=label, executive_summary=summary,
            key_developments=claims, emerging_themes=analysis.themes, sentiment=analysis.sentiment,
            risks=risks, uncertainties=uncertainties, sources=sources, validation=validation,
        )
        briefing.markdown = self.render_markdown(briefing, analysis)
        briefing.email_draft = self.render_email(briefing)
        return briefing

    @staticmethod
    def render_markdown(b: Briefing, analysis: AnalysisOutput) -> str:
        L: list[str] = []
        if b.is_sample:
            L += ["> **SAMPLE DATA - not real news.**", ""]
        L += [f"# Market Intelligence Briefing - {b.generated_at:%Y-%m-%d}", "",
              f"**Reporting period:** {_fmt(b.period_start)} to {_fmt(b.period_end)}  ",
              f"**Topics:** {', '.join(b.topics)}  ", f"**Generation mode:** {b.mode_label}", "",
              "## Executive summary", "", b.executive_summary, "", "## Key developments", ""]
        for i, c in enumerate(b.key_developments, 1):
            tag = {"verified_fact": "corroborated by multiple publishers",
                   "source_attributed": "single-source, attributed",
                   "analytical_interpretation": "analytical interpretation"}[c.kind]
            refs = ", ".join(f"[{n}]({u})" for n, u in enumerate(c.source_urls, 1))
            L += [f"{i}. **{c.text}** - _{', '.join(c.publishers)}; {_fmt(c.published_at)}; {tag}_  ",
                  f"   Why it may matter: {c.why_it_matters}  ", f"   Sources: {refs}"]
        L += ["", "## Emerging themes", ""]
        if b.emerging_themes:
            for t in b.emerging_themes:
                note = analysis.llm_notes.get(t.name)
                L.append(f"- **{t.name}** - {t.article_count} articles, {len(t.publishers)} publisher(s), "
                         f"avg sentiment {t.avg_sentiment:+.2f}")
                if note:
                    L.append(f"  - Interpretation (AI-generated, speculative): {note}")
        else:
            L.append("- No recurring theme met the minimum evidence threshold.")
        s = b.sentiment
        L += ["", "## Sentiment overview", "",
              f"Engine: {s.engine}. Positive {s.positive} / Neutral {s.neutral} / Negative {s.negative}; "
              f"mean {s.mean_score:+.2f}.", "", f"_{SENTIMENT_DISCLAIMER}_", "", "## Risks", ""]
        L += [f"- {r}" for r in b.risks] or ["- No strongly negative-toned stories were detected."]
        L += ["", "## Uncertainties", ""] + [f"- {u}" for u in b.uncertainties]
        L += ["", "## Verification summary", "",
              f"Passed: {b.validation.passed}; revisions: {b.validation.revisions}; "
              f"unsupported claims removed: {b.validation.unsupported_removed}."]
        L += [f"- Flag: {f}" for f in b.validation.flags]
        L += ["", "## Source references", ""]
        for a in b.sources:
            L.append(f"- {a.publisher} - [{a.title}]({a.url}) ({_fmt(a.published_at)}; collected {_fmt(a.collected_at)})")
        L += ["", "---", "Headlines and links belong to their publishers; this report quotes only headlines "
              "and short extracts. Not investment advice."]
        return "\n".join(L)

    @staticmethod
    def render_email(b: Briefing) -> str:
        lines = [f"Subject: Daily Market Intelligence Briefing - {b.generated_at:%Y-%m-%d}", "",
                 "[DRAFT - NOT SENT. Review before sending.]", "", "Hello,", "", b.executive_summary, "",
                 "Key developments:"]
        for c in b.key_developments[:5]:
            lines.append(f"- {c.text} ({', '.join(c.publishers)}) {c.source_urls[0]}")
        lines += ["", f"Sentiment signals are analytical, not forecasts. Mode: {b.mode_label}.", "", "Regards"]
        return "\n".join(lines)
