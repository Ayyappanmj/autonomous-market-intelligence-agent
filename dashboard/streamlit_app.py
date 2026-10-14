"""Streamlit dashboard. Talks to the FastAPI backend over HTTP (API_BASE_URL)."""
import os

import pandas as pd
import requests
import streamlit as st

API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TOPICS = ["ai", "technology", "markets", "business", "energy", "economy"]
DISCLAIMER = ("Sentiment scores are analytical signals, not guaranteed market forecasts or "
              "investment recommendations.")

st.set_page_config(page_title="Market Intelligence Agent", page_icon="📊", layout="wide")
st.markdown(
    """<style>
    .block-container{padding-top:2rem;max-width:1200px}
    .card{border:1px solid rgba(128,128,128,.3);border-radius:10px;padding:.8rem 1rem;margin-bottom:.6rem}
    .meta{opacity:.7;font-size:.85rem}
    @media (max-width:640px){.block-container{padding:1rem .6rem}}
    </style>""",
    unsafe_allow_html=True,
)


def api(method: str, path: str, **kw):
    """Return (data, error_message)."""
    try:
        r = requests.request(method, f"{API}{path}", timeout=kw.pop("timeout", 15), **kw)
        if r.status_code == 404:
            return None, None
        if r.status_code >= 400:
            try:
                msg = r.json().get("detail", "Request failed.")
            except ValueError:
                msg = "Request failed."
            return None, f"{msg} (HTTP {r.status_code})"
        return r.json(), None
    except requests.RequestException:
        return None, "Cannot reach the API. If the service just woke up, wait a few seconds and retry."


st.title("📊 Autonomous Market Intelligence Agent")
st.caption("Research → Deduplication → Analysis → Verification → Briefing → Final validation")
st.info(DISCLAIMER)

health, herr = api("GET", "/health")
with st.sidebar:
    st.header("System")
    if health:
        st.success(f"API {health['status']} · v{health['version']}")
        st.write("LLM: " + (f"{health.get('llm_provider')} / {health.get('llm_model')} (optional)" if health["llm_configured"] else "off (free fallback)"))
    else:
        st.error(herr or "API unavailable")
    feeds_data, _ = api("GET", "/api/v1/feeds")
    if feeds_data:
        with st.expander(f"News sources ({len(feeds_data['items'])})"):
            for f in feeds_data["items"]:
                st.caption(f"{f['name']} - {', '.join(f['topics']) or 'all topics'}")
    st.header("Generate")
    topics = st.multiselect("Topics", TOPICS, default=["ai", "technology", "markets"])
    days = st.slider("Date range (last N days)", 1, 14, 2)
    max_articles = st.slider("Max articles", 5, 100, 40)
    use_llm = st.checkbox("Use LLM if configured", value=False,
                          disabled=not (health and health["llm_configured"]))
    go = st.button("Generate Daily Briefing", type="primary", use_container_width=True,
                   disabled=not topics or not health)
    st.caption("Free hosting note: the service may sleep when idle and history can reset after a restart. "
               "Download reports to keep them.")

if go:
    with st.spinner("Agents are working: fetching feeds, analysing, verifying (can take ~30-60 s)..."):
        data, err = api("POST", "/api/v1/briefings/generate", timeout=180,
                        json={"topics": topics, "days": days, "max_articles": max_articles, "use_llm": use_llm})
    if err:
        st.error(err)
    else:
        st.success("Briefing generated.")

briefing, berr = api("GET", "/api/v1/briefings/latest")
status, _ = api("GET", "/api/v1/agents/status")
tab_brief, tab_news, tab_charts, tab_agents, tab_hist = st.tabs(
    ["Briefing", "News", "Analytics", "Agent progress", "History"])

with tab_brief:
    if berr:
        st.error(berr)
    elif not briefing:
        st.info("No briefing yet. Choose topics in the sidebar and press **Generate Daily Briefing**.")
    else:
        if briefing.get("is_sample"):
            st.warning("SAMPLE DATA - not real news.")
        st.caption(f"Mode: {briefing['mode_label']}")
        c1, c2 = st.columns(2)
        c1.download_button("⬇ Markdown", briefing["markdown"], f"briefing_{briefing['id']}.md",
                           "text/markdown", use_container_width=True)
        import json as _json
        c2.download_button("⬇ JSON", _json.dumps(briefing, indent=2), f"briefing_{briefing['id']}.json",
                           "application/json", use_container_width=True)
        st.markdown(briefing["markdown"])
        with st.expander("Email-ready draft (never sent automatically)"):
            st.code(briefing["email_draft"], language="text")
        with st.expander("Verification details"):
            v = briefing["validation"]
            st.write(f"Passed: **{v['passed']}** · revisions: {v['revisions']} · removed: {v['unsupported_removed']}")
            if v["checks"]:
                st.dataframe(pd.DataFrame(v["checks"])[["status", "claim", "detail"]], use_container_width=True)

with tab_news:
    topic_filter = st.multiselect("Filter by topic", TOPICS, key="nf")
    page = st.number_input("Page", 1, 100, 1)
    news, nerr = api("GET", "/api/v1/news", params={"topic": topic_filter, "page": page, "page_size": 10})
    if nerr:
        st.error(nerr)
    elif not news or not news["items"]:
        st.info("No articles stored yet. Generate a briefing first.")
    else:
        st.caption(f"{news['total']} articles")
        for a in news["items"]:
            date = (a["published_at"] or "date not provided")[:16].replace("T", " ")
            st.markdown(
                f"<div class='card'><b>{a['title'].replace('<','&lt;')}</b><div class='meta'>"
                f"{a['publisher']} · {date} · {', '.join(a['topics'])} · {a.get('sentiment_label') or 'n/a'}"
                f"</div><a href='{a['url']}' target='_blank' rel='noopener noreferrer'>Read at source ↗</a></div>",
                unsafe_allow_html=True)

with tab_charts:
    an, aerr = api("GET", "/api/v1/analytics")
    if aerr:
        st.error(aerr)
    elif not an or not an["article_count"]:
        st.info("No analytics yet.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Articles", an["article_count"])
        m2.metric("Mean sentiment signal", f"{an['mean_sentiment']:+.2f}")
        m3.metric("Publishers", len(an["source_coverage"]))
        a, b = st.columns(2)
        a.subheader("Sentiment distribution")
        a.bar_chart(pd.Series(an["sentiment_distribution"]))
        b.subheader("Topic frequency")
        b.bar_chart(pd.Series(an["topic_distribution"]))
        st.subheader("Source coverage")
        st.bar_chart(pd.Series(an["source_coverage"]))
        if briefing and briefing["emerging_themes"]:
            st.subheader("Trending themes and evidence")
            for t in briefing["emerging_themes"]:
                with st.expander(f"{t['name']} - {t['article_count']} articles"):
                    st.write(f"Publishers: {', '.join(t['publishers'])}; avg sentiment {t['avg_sentiment']:+.2f}")
                    for u in t["evidence"]:
                        st.markdown(f"- {u}")
        st.caption(DISCLAIMER)

with tab_agents:
    if not status or status["state"] == "idle":
        st.info("No workflow has run yet.")
    else:
        st.write(f"Run `{status['run_id']}` · state **{status['state']}** · mode {status.get('mode')}")
        icons = {"completed": "✅", "running": "⏳", "failed": "❌", "pending": "⚪", "skipped": "⏭"}
        for s in status["stages"]:
            st.write(f"{icons.get(s['state'], '•')} **{s['name']}** - {s['detail'] or s['state']}"
                     + (f" · error: {s['error']}" if s.get("error") else ""))
        for e in status["errors"]:
            st.warning(e)

with tab_hist:
    hist, herr2 = api("GET", "/api/v1/briefings/history")
    if herr2:
        st.error(herr2)
    elif not hist or not hist["items"]:
        st.info("No history. (On free hosting, history resets when the service restarts.)")
    else:
        st.dataframe(pd.DataFrame(hist["items"]), use_container_width=True)
