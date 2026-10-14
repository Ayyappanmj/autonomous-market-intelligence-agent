"""Headless daily run: fetch live feeds, build a briefing, write Markdown + JSON files.

Used by .github/workflows/daily-briefing.yml so history lives in git (free, persistent) instead of an
ephemeral server disk. Uses Gemini/LLM mode automatically when credentials are configured.

  python scripts/run_briefing.py [--topics ai markets] [--days 1] [--no-llm] [--out briefings]
"""
import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.llm import build_llm_client  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.ingestion.rss_reader import FeedFetcher  # noqa: E402
from app.schemas.briefing import TOPICS, GenerateRequest  # noqa: E402
from app.storage.repository import SQLiteRepository  # noqa: E402
from app.utils.logging import configure_logging  # noqa: E402
from app.workflows.briefing_workflow import BriefingWorkflow, WorkflowError  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", nargs="+", default=["ai", "technology", "markets", "economy"], choices=TOPICS)
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--out", default="briefings")
    args = ap.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)
    repo = SQLiteRepository(str(Path(tempfile.mkdtemp()) / "run.db"))
    repo.init()
    llm = None if args.no_llm else build_llm_client(settings)
    wf = BriefingWorkflow(settings, repo, FeedFetcher(settings), llm)
    try:
        b = wf.run(GenerateRequest(topics=args.topics, days=args.days, use_llm=llm is not None))
    except WorkflowError as exc:
        print(f"briefing failed: {exc}", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (out / f"{stamp}.md").write_text(b.markdown, encoding="utf-8")
    (out / f"{stamp}.json").write_text(json.dumps(json.loads(b.model_dump_json()), indent=2), encoding="utf-8")
    (out / "latest.md").write_text(b.markdown, encoding="utf-8")
    print(f"wrote {out}/{stamp}.md mode={b.mode} claims={len(b.key_developments)} passed={b.validation.passed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
