"""Generate sample_data/sample_briefing.{md,json} from FICTIONAL, clearly labelled sample articles.

Runs the real workflow offline (no network): feeds are served from an in-memory fake session.
Usage:  python scripts/generate_sample.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.analysis_agent import AnalysisOutput  # noqa: E402
from app.agents.briefing_agent import BriefingAgent  # noqa: E402
from app.config import Settings  # noqa: E402
from app.ingestion.rss_reader import FeedFetcher  # noqa: E402
from app.schemas.briefing import GenerateRequest  # noqa: E402
from app.storage.repository import SQLiteRepository  # noqa: E402
from app.workflows.briefing_workflow import BriefingWorkflow  # noqa: E402

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)

# FICTIONAL companies and events. Publishers are fictional too. Nothing here is real news.
SAMPLE = {
    "Sample Daily Ledger / Business": [
        ("Fictional Helios Chips shares surge as AI server demand grows", "https://sample.invalid/ledger/helios-surge",
         "Investors cheer strong AI server orders reported by Helios Chips.", "Thu, 15 Jan 2026 09:30:00 GMT"),
        ("Sample Northwind Energy warns of weaker crude demand", "https://sample.invalid/ledger/northwind-warns",
         "Northwind Energy flagged weaker demand and rising uncertainty for crude oil.", "Thu, 15 Jan 2026 08:10:00 GMT"),
        ("Central bank of Samplia holds interest rates steady", "https://sample.invalid/ledger/samplia-rates",
         "Policy makers cited inflation risks and cooling growth in the economy.", "Wed, 14 Jan 2026 16:00:00 GMT"),
        ("Fictional retailer Brightmart announces layoffs amid weak sales", "https://sample.invalid/ledger/brightmart",
         "Brightmart plans job cuts after weak holiday sales.", "Wed, 14 Jan 2026 11:00:00 GMT"),
    ],
    "Example Tech Wire / Technology": [
        ("Fictional Helios Chips shares surge as AI server demand grows", "https://sample.invalid/techwire/helios",
         "AI server demand boosts Helios Chips.", "Thu, 15 Jan 2026 10:15:00 GMT"),
        ("Startup Lumen Labs launches new AI assistant for software teams", "https://sample.invalid/techwire/lumen",
         "A new AI coding assistant aimed at software teams.", "Thu, 15 Jan 2026 07:45:00 GMT"),
        ("Regulators open probe into Sample Cloud Corp data breach", "https://sample.invalid/techwire/cloud-breach",
         "An investigation follows a breach at Sample Cloud Corp.", "Wed, 14 Jan 2026 14:20:00 GMT"),
        ("AI data centre power demand raises grid concerns", "https://sample.invalid/techwire/dc-power",
         "Electricity demand from AI data centres is raising concerns.", "Tue, 13 Jan 2026 18:00:00 GMT"),
    ],
    "Placeholder Markets Post / Markets": [
        ("Samplia stocks rally as earnings beat expectations", "https://sample.invalid/post/stocks-rally",
         "Equities gained after strong earnings.", "Thu, 15 Jan 2026 06:30:00 GMT"),
        ("Oil falls as Northwind Energy flags weaker crude demand", "https://sample.invalid/post/oil-falls",
         "Crude prices slid on demand concerns after Northwind Energy's warning.", "Thu, 15 Jan 2026 09:00:00 GMT"),
        ("Investors weigh AI data centre investment and power concerns", "https://sample.invalid/post/ai-invest",
         "AI investment continues while power supply concerns grow.", "Wed, 14 Jan 2026 19:30:00 GMT"),
    ],
}


def rss(items):
    body = "".join(f"<item><title>{t}</title><link>{u}</link><description>{d}</description>"
                   f"<pubDate>{p}</pubDate></item>" for t, u, d, p in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>s</title>{body}</channel></rss>'.encode()


class _Resp:
    status_code, headers = 200, {}

    def __init__(self, content):
        self.content = content

    def iter_content(self, chunk_size=16384):
        yield self.content


class _Session:
    def __init__(self, routes):
        self.routes = routes

    def get(self, url, **_):
        return _Resp(self.routes[url])


def main() -> None:
    feeds = {name: f"https://feeds.sample.invalid/{i}" for i, name in enumerate(SAMPLE)}
    routes = {feeds[name]: rss(items) for name, items in SAMPLE.items()}
    settings = Settings(allow_private_hosts=True, feeds=feeds, http_retries=0, cache_ttl_s=0)
    repo = SQLiteRepository(":memory:")
    repo.init()
    wf = BriefingWorkflow(settings, repo, FeedFetcher(settings, _Session(routes)), None)
    b = wf.run(GenerateRequest(topics=["ai", "technology", "markets", "business", "energy", "economy"], days=3), now=NOW)
    b.is_sample = True
    b.markdown = BriefingAgent.render_markdown(b, AnalysisOutput())
    out = Path(__file__).resolve().parents[1] / "sample_data"
    out.mkdir(exist_ok=True)
    (out / "sample_briefing.md").write_text(b.markdown, encoding="utf-8")
    (out / "sample_briefing.json").write_text(json.dumps(json.loads(b.model_dump_json()), indent=2), encoding="utf-8")
    print(f"wrote sample briefing {b.id} ({len(b.key_developments)} developments, passed={b.validation.passed})")


if __name__ == "__main__":
    main()
