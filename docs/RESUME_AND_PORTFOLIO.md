# Resume and portfolio guide

## What makes this project resume-ready (do these, in order)
1. **Get CI green and add the badge.** Push, open the Actions tab, fix anything red, then add `![CI](https://github.com/<you>/<repo>/actions/workflows/ci.yml/badge.svg)` to the README top. A green badge is the first thing a reviewer checks.
2. **Deploy and put the live URL at the top of the README.** Wake it before sharing links (free services sleep). Add a 30-60 s screen recording or GIF of generating a briefing.
3. **Turn on Gemini mode and the daily workflow.** A repo with a `briefings/` folder of real, dated, verified briefings is proof that it runs unattended.
4. **Generate real metrics.** Run `python scripts/evaluate.py --live --write`, and build a real labelled sentiment set (100+ headlines, labelled by you and a friend; report agreement). Then your bullets can contain numbers you can defend in an interview.
5. **Write down decisions** (a short `docs/DECISIONS.md`): why a custom pipeline instead of CrewAI/LangGraph, why verification is deterministic, why extractive claims, why a gateway. Interviewers ask "why", not "what".
6. **Know the weak spots and say them first:** rule-based sentiment is a baseline; verification checks wording overlap, not truth; free tier sleeps and loses its disk; WebSocket gateway is minimal.

## Stretch features that impress (pick one or two, finish them)
- Compare the rule-based sentiment to Gemini and to a small finance model on your labelled set, and report the trade-offs.
- A LangGraph version of the workflow side by side, with timing and complexity notes.
- PostgreSQL repository (Neon/Supabase free tier) behind the existing `Repository` interface.
- API keys + per-key rate limits, request IDs and Prometheus-style metrics.
- Embedding-based clustering to replace term-frequency themes.

## Resume bullets (replace bracketed values with numbers you measured, or delete the clause)
- Built a four-agent news-intelligence pipeline (FastAPI, Streamlit, Pydantic, SQLite) that verifies every briefing claim against retrieved sources; [N]% of claims in [N] test runs were source-supported and unsupported claims were removed automatically.
- Integrated Gemini (free tier) behind an adapter with quota budgeting, retry/backoff and output grounding checks; falls back to a deterministic mode with no paid API.
- Hardened ingestion (SSRF-safe fetching, defusedxml, size/time limits, prompt-injection screening) and wrote [N] network-free pytest cases with GitHub Actions CI.
- Automated daily briefings with a scheduled GitHub Actions workflow and deployed the API + dashboard on one Render free-tier service through a WebSocket-aware gateway.

## Portfolio summary (2 sentences)
A source-grounded market news briefing agent that checks each claim against retrieved articles before writing, runs free of charge, and optionally uses Gemini for richer summaries. It shows multi-agent orchestration, defensive ingestion, API design, testing and zero-budget deployment.

Only claim what you have run: no deployment URL, user counts, benchmarks or test totals until you have real ones.
