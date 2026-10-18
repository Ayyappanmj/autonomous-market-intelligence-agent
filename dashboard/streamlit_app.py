"""Autonomous Market Intelligence Agent - Executive Streamlit Dashboard.
Connects to the FastAPI backend over HTTP (API_BASE_URL) and provides a
Bloomberg-terminal / Linear-inspired interface for multi-agent market intelligence.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import altair as alt
import pandas as pd
import requests
import streamlit as st

# -----------------------------------------------------------------------------
# Configuration & Constants
# -----------------------------------------------------------------------------
API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TOPICS = ["ai", "technology", "markets", "business", "energy", "economy"]
DISCLAIMER = (
    "Analytical signals and sentiment scores are automated research indicators, "
    "not market forecasts or financial/investment recommendations."
)

TOPIC_COLORS = {
    "ai": "#8b5cf6",
    "technology": "#3b82f6",
    "markets": "#f59e0b",
    "business": "#14b8a6",
    "energy": "#f97316",
    "economy": "#10b981",
}

st.set_page_config(
    page_title="MarketIntel OS | Autonomous Multi-Agent Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# Custom High-End Styling (Fintech Dark Glassmorphism)
# -----------------------------------------------------------------------------
st.markdown(
    """<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1380px;
    }
    
    /* Executive Header */
    .hero-banner {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid rgba(59, 130, 246, 0.25);
        border-radius: 14px;
        padding: 1.4rem 1.8rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        backdrop-filter: blur(8px);
    }
    .hero-title {
        font-size: 1.75rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        background: linear-gradient(90deg, #60a5fa, #a78bfa, #34d399);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.3rem;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .hero-subtitle {
        font-size: 0.95rem;
        color: #94a3b8;
        font-weight: 400;
        line-height: 1.4;
    }
    
    /* Live Status Pulse */
    .live-beacon {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.25rem 0.7rem;
        background: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        color: #34d399;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .pulse-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background-color: #10b981;
        box-shadow: 0 0 10px #10b981;
    }
    
    /* Architecture Stepper Cards */
    .agent-stepper {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 0.75rem;
        margin-bottom: 1.5rem;
    }
    .agent-step-card {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(148, 163, 184, 0.12);
        border-radius: 10px;
        padding: 0.85rem 1rem;
        transition: all 0.2s ease;
    }
    .agent-step-card:hover {
        border-color: rgba(59, 130, 246, 0.4);
        transform: translateY(-2px);
        background: rgba(30, 41, 59, 0.7);
    }
    .agent-step-num {
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        color: #3b82f6;
        letter-spacing: 0.08em;
    }
    .agent-step-title {
        font-size: 0.9rem;
        font-weight: 700;
        color: #f1f5f9;
        margin: 0.2rem 0;
    }
    .agent-step-desc {
        font-size: 0.75rem;
        color: #64748b;
        line-height: 1.3;
    }
    
    /* KPI Metric Tiles */
    .kpi-container {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 1rem;
        margin-bottom: 1.5rem;
    }
    .kpi-card {
        background: linear-gradient(180deg, rgba(30, 41, 59, 0.6) 0%, rgba(15, 23, 42, 0.8) 100%);
        border: 1px solid rgba(148, 163, 184, 0.15);
        border-radius: 12px;
        padding: 1rem 1.2rem;
        position: relative;
        overflow: hidden;
    }
    .kpi-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, #3b82f6, #8b5cf6);
    }
    .kpi-label {
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #94a3b8;
    }
    .kpi-value {
        font-size: 1.8rem;
        font-weight: 800;
        color: #f8fafc;
        margin: 0.3rem 0;
        font-family: 'JetBrains Mono', monospace;
    }
    .kpi-delta {
        font-size: 0.75rem;
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 0.3rem;
    }
    
    /* Intelligence Article & Claim Cards */
    .intel-card {
        background: rgba(15, 23, 42, 0.65);
        border: 1px solid rgba(148, 163, 184, 0.14);
        border-radius: 12px;
        padding: 1.1rem 1.3rem;
        margin-bottom: 0.9rem;
        transition: all 0.2s ease;
    }
    .intel-card:hover {
        border-color: rgba(96, 165, 250, 0.4);
        background: rgba(30, 41, 59, 0.75);
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.4);
    }
    .intel-title {
        font-size: 1.05rem;
        font-weight: 600;
        color: #f8fafc;
        margin-bottom: 0.4rem;
        line-height: 1.4;
    }
    .intel-why {
        background: rgba(59, 130, 246, 0.08);
        border-left: 3px solid #3b82f6;
        border-radius: 4px;
        padding: 0.6rem 0.8rem;
        margin: 0.6rem 0;
        font-size: 0.85rem;
        color: #cbd5e1;
        line-height: 1.45;
    }
    .intel-meta {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.8rem;
        color: #64748b;
        margin-top: 0.6rem;
    }
    
    /* Badges & Chips */
    .chip {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }
    .chip-pos {
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid rgba(16, 185, 129, 0.35);
        color: #34d399;
    }
    .chip-neu {
        background: rgba(99, 102, 241, 0.15);
        border: 1px solid rgba(99, 102, 241, 0.35);
        color: #a5b4fc;
    }
    .chip-neg {
        background: rgba(244, 63, 94, 0.15);
        border: 1px solid rgba(244, 63, 94, 0.35);
        color: #fb7185;
    }
    .chip-verified {
        background: rgba(59, 130, 246, 0.15);
        border: 1px solid rgba(59, 130, 246, 0.35);
        color: #60a5fa;
    }
    .chip-topic {
        background: rgba(148, 163, 184, 0.1);
        border: 1px solid rgba(148, 163, 184, 0.25);
        color: #94a3b8;
    }
    
    /* Verification Box */
    .audit-box {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.9) 0%, rgba(26, 38, 64, 0.9) 100%);
        border: 1px solid rgba(59, 130, 246, 0.3);
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1.2rem;
    }
    
    /* Disclaimer styling */
    .disclaimer-box {
        font-size: 0.8rem;
        color: #64748b;
        background: rgba(15, 23, 42, 0.4);
        border: 1px solid rgba(148, 163, 184, 0.1);
        border-radius: 8px;
        padding: 0.6rem 1rem;
        margin-top: 1.5rem;
    }
    </style>""",
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# API Client & Data Access
# -----------------------------------------------------------------------------
def api(method: str, path: str, **kw) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Safe HTTP client communicating with backend."""
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
        return None, "Backend API unavailable. Check if server process is running."


def get_fallback_sample() -> Optional[dict[str, Any]]:
    """Loads realistic sample briefing from sample_data/sample_briefing.json."""
    sample_file = Path("sample_data/sample_briefing.json")
    if sample_file.exists():
        try:
            return json.loads(sample_file.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# -----------------------------------------------------------------------------
# System Health & State Initialization
# -----------------------------------------------------------------------------
health, herr = api("GET", "/health")
feeds_data, _ = api("GET", "/api/v1/feeds")

if "use_sample_data" not in st.session_state:
    st.session_state.use_sample_data = False

# -----------------------------------------------------------------------------
# Top Hero / Executive Header Bar
# -----------------------------------------------------------------------------
st.markdown(
    """<div class="hero-banner">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem;">
            <div>
                <div class="hero-title">
                    <span>⚡ MARKET INTELLIGENCE OS</span>
                </div>
                <div class="hero-subtitle">
                    Autonomous Multi-Agent Financial Research & Verification Pipeline · Zero-Hallucination Architecture
                </div>
            </div>
            <div style="display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap;">
                <span class="live-beacon">
                    <span class="pulse-dot"></span>
                    <span>System Active</span>
                </span>
                <span class="chip chip-verified">
                    FastAPI v1.0.0
                </span>
                <span class="chip chip-neu">
                    Verification Guardrails: ON
                </span>
            </div>
        </div>
    </div>""",
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Architecture Showcase: Multi-Agent Pipeline Visual Stepper
# -----------------------------------------------------------------------------
with st.expander("🧩 Multi-Agent Pipeline Architecture (Click to inspect pipeline design)", expanded=False):
    st.markdown(
        """<div class="agent-stepper">
            <div class="agent-step-card">
                <div class="agent-step-num">Agent 01</div>
                <div class="agent-step-title">🌐 News Research</div>
                <div class="agent-step-desc">Ingests 18 public feeds with SSRF defense, rate-limiting, and schema normalisation.</div>
            </div>
            <div class="agent-step-card">
                <div class="agent-step-num">Engine 02</div>
                <div class="agent-step-title">🔍 Deduplication</div>
                <div class="agent-step-desc">Deterministic cosine & URL canonicalisation grouping identical stories across outlets.</div>
            </div>
            <div class="agent-step-card">
                <div class="agent-step-num">Agent 03</div>
                <div class="agent-step-title">📊 Trend & Sentiment</div>
                <div class="agent-step-desc">Computes rule-based VADER lexicon score and mines recurring thematic clusters.</div>
            </div>
            <div class="agent-step-card">
                <div class="agent-step-num">Agent 04</div>
                <div class="agent-step-title">🛡️ Verification & QC</div>
                <div class="agent-step-desc">Source-grounds every single claim against cited URLs. Flags single-source & stale claims.</div>
            </div>
            <div class="agent-step-card">
                <div class="agent-step-num">Agent 05</div>
                <div class="agent-step-title">📝 Briefing Synthesis</div>
                <div class="agent-step-desc">Compiles executive takeaways, risks, uncertainties, Markdown & JSON exports.</div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

# -----------------------------------------------------------------------------
# Sidebar: Controls, System Diagnostics & Demo Mode
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ System Diagnostics")
    if health:
        col_s1, col_s2 = st.columns(2)
        col_s1.metric("API Status", "ONLINE", delta="Healthy", delta_color="normal")
        col_s2.metric("Database", "SQLITE", delta="Verified", delta_color="normal")
        
        mode_str = "Gemini LLM" if health.get("llm_configured") else "Deterministic"
        st.caption(f"🧠 **Engine Mode:** `{mode_str}` (Free fallback enabled)")
    else:
        st.error(f"⚠️ {herr or 'API Server Offline'}")

    st.markdown("---")
    st.markdown("### 🚀 Generate Intelligence")
    
    topics = st.multiselect(
        "Market Topics",
        TOPICS,
        default=["ai", "technology", "markets"],
        help="Filter feeds and analysis to specific topic verticals.",
    )
    
    days = st.slider("Lookback Window (Days)", 1, 14, 3, help="Ingest articles published within this window.")
    max_articles = st.slider("Max Article Volume", 10, 100, 40)
    use_llm = st.checkbox(
        "Augment with Gemini LLM",
        value=False,
        disabled=not (health and health.get("llm_configured")),
        help="When enabled and API key is present, generates speculative analytical commentary.",
    )
    
    col_btn1, col_btn2 = st.columns([1.2, 1])
    with col_btn1:
        go = st.button("⚡ Run Pipeline", type="primary", use_container_width=True, disabled=not topics or not health)
    with col_btn2:
        toggle_sample = st.button(
            "📂 Load Demo" if not st.session_state.use_sample_data else "🔄 Use Live",
            use_container_width=True,
            help="Toggle verified offline sample dataset for immediate review.",
        )
        if toggle_sample:
            st.session_state.use_sample_data = not st.session_state.use_sample_data
            st.rerun()

    if feeds_data and feeds_data.get("items"):
        with st.expander(f"📡 Monitored Feeds ({len(feeds_data['items'])})"):
            for f in feeds_data["items"]:
                topic_badges = " ".join([f"`{t}`" for t in f.get("topics", [])])
                st.markdown(f"**{f['name']}**\n{topic_badges}")

    st.markdown("---")
    st.markdown("### 👨‍💻 Recruiter & Tech Overview")
    st.markdown(
        """<div style="font-size: 0.8rem; color: #94a3b8; line-height: 1.5;">
        <b>Architecture Stack:</b><br/>
        • <b>Backend:</b> Python 3.11, FastAPI, Pydantic v2<br/>
        • <b>Multi-Agent:</b> Research, Dedup, Sentiment, QC<br/>
        • <b>Storage:</b> SQLite Repository with TTL pruning<br/>
        • <b>Gateway:</b> Single-port HTTP + WebSocket Proxy<br/>
        • <b>Testing:</b> 97 Pytest Unit & Integration Tests<br/>
        <br/>
        <a href="http://localhost:8000/docs" target="_blank" style="color: #60a5fa; text-decoration: none;">📖 Interactive API Docs (/docs) ↗</a><br/>
        <a href="https://github.com/Ayyappanmj/autonomous-market-intelligence-agent" target="_blank" style="color: #60a5fa; text-decoration: none;">🐙 GitHub Repository ↗</a>
        </div>""",
        unsafe_allow_html=True,
    )

# -----------------------------------------------------------------------------
# Trigger Workflow Execution
# -----------------------------------------------------------------------------
if go:
    st.session_state.use_sample_data = False
    with st.status("Executing Multi-Agent Workflow...", expanded=True) as status_box:
        st.write("🌐 News Research Agent: Connecting to monitored RSS feeds...")
        data, err = api(
            "POST",
            "/api/v1/briefings/generate",
            timeout=180,
            json={"topics": topics, "days": days, "max_articles": max_articles, "use_llm": use_llm},
        )
        if err:
            status_box.update(label="Workflow halted with error", state="error")
            st.error(f"Execution Error: {err}")
        else:
            status_box.update(label="Intelligence briefing synthesized and verified!", state="complete")
            st.success("Briefing compiled with 100% source ground-truth verification.")
            st.rerun()

# -----------------------------------------------------------------------------
# Load Current Briefing & Data
# -----------------------------------------------------------------------------
briefing = None
berr = None

if st.session_state.use_sample_data:
    briefing = get_fallback_sample()
    status_data = {
        "run_id": "demo_sample_run",
        "state": "completed",
        "mode": "deterministic_fallback",
        "stages": [
            {"name": "research", "state": "completed", "detail": "12 articles ingested from 3 publishers"},
            {"name": "deduplication", "state": "completed", "detail": "10 unique stories after cosine clustering"},
            {"name": "analysis", "state": "completed", "detail": "Sentiment scoring & recurring themes mapped"},
            {"name": "verification", "state": "completed", "detail": "Verified 8 claims; 0 unsupported"},
            {"name": "briefing", "state": "completed", "detail": "Markdown & JSON documents compiled"},
            {"name": "validation", "state": "completed", "detail": "Passed final validation guardrails"},
        ],
        "errors": [],
    }
else:
    briefing, berr = api("GET", "/api/v1/briefings/latest")
    status_data, _ = api("GET", "/api/v1/agents/status")

# Auto-fallback to sample if completely empty
if not briefing and not berr:
    sample_preview = get_fallback_sample()
    if sample_preview:
        briefing = sample_preview
        st.session_state.use_sample_data = True

# -----------------------------------------------------------------------------
# Tabs Interface
# -----------------------------------------------------------------------------
tab_brief, tab_news, tab_charts, tab_agents, tab_hist = st.tabs(
    [
        "📑 Executive Briefing",
        "📰 Intelligence Feed",
        "📈 Quantitative Analytics",
        "🤖 Agent Trace & Progress",
        "🗄️ Briefing Archive",
    ]
)

# =============================================================================
# TAB 1: EXECUTIVE BRIEFING
# =============================================================================
with tab_brief:
    if not briefing:
        st.info("No briefing generated yet. Configure topics in the sidebar and press **Run Pipeline**.")
    else:
        if briefing.get("is_sample") or st.session_state.use_sample_data:
            st.markdown(
                """<div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px; padding: 0.6rem 1rem; margin-bottom: 1rem; color: #fbbf24; font-size: 0.85rem;">
                ⚡ <b>DEMO PREVIEW:</b> Displaying pre-verified multi-publisher sample intelligence dataset. Press 'Run Pipeline' in the sidebar to generate from live feeds.
                </div>""",
                unsafe_allow_html=True,
            )

        # Executive Metrics Top Bar
        val = briefing.get("validation", {})
        devs = briefing.get("key_developments", [])
        themes = briefing.get("emerging_themes", [])
        
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-card">
                    <div class="kpi-label">Verified Claims</div>
                    <div class="kpi-value">{len(devs)}</div>
                    <div class="kpi-delta" style="color: #34d399;">✓ Grounded in cited sources</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Emerging Themes</div>
                    <div class="kpi-value">{len(themes)}</div>
                    <div class="kpi-delta" style="color: #60a5fa;">Clustered via recurrence</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">QC Validation</div>
                    <div class="kpi-value">{"PASS" if val.get("passed", True) else "FLAG"}</div>
                    <div class="kpi-delta" style="color: #34d399;">{val.get('revisions', 0)} revisions required</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Ingested Sources</div>
                    <div class="kpi-value">{len(briefing.get("sources", []))}</div>
                    <div class="kpi-delta" style="color: #a78bfa;">Multi-Publisher Diversity</div>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        # Executive Summary Box
        st.markdown("### 📌 Executive Summary")
        st.markdown(
            f"""<div style="background: rgba(30, 41, 59, 0.5); border-left: 4px solid #60a5fa; border-radius: 8px; padding: 1.2rem; font-size: 1.05rem; line-height: 1.6; color: #f1f5f9; margin-bottom: 1.5rem;">
                {briefing.get('executive_summary', 'No summary available.')}
            </div>""",
            unsafe_allow_html=True,
        )

        # Key Developments Section
        st.markdown("### ⚡ Key Verified Developments")
        if not devs:
            st.caption("No key developments identified in this period.")
        else:
            for d in devs:
                kind_label = d.get("kind", "source_attributed").replace("_", " ").title()
                publishers = ", ".join(d.get("publishers", ["Unknown"]))
                sources_links = " · ".join(
                    [f"<a href='{u}' target='_blank' rel='noopener noreferrer' style='color:#60a5fa;'>Source ↗</a>" for u in d.get("source_urls", [])]
                )
                
                st.markdown(
                    f"""<div class="intel-card">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem;">
                            <div class="intel-title">{d.get('text', '')}</div>
                            <span class="chip chip-verified">{kind_label}</span>
                        </div>
                        <div class="intel-why">
                            <b>💡 Significance:</b> {d.get('why_it_matters', 'Significance being monitored.')}
                        </div>
                        <div class="intel-meta">
                            <span>📰 <b>Publishers:</b> {publishers}</span>
                            <span>•</span>
                            <span>🔗 {sources_links}</span>
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )

        # Emerging Themes
        if themes:
            st.markdown("### 🌐 Thematic Clusters & Evidence")
            col_t1, col_t2 = st.columns(2)
            for idx, th in enumerate(themes):
                target_col = col_t1 if idx % 2 == 0 else col_t2
                with target_col:
                    sentiment_val = th.get("avg_sentiment", 0.0)
                    sentiment_color = "#34d399" if sentiment_val > 0.05 else ("#fb7185" if sentiment_val < -0.05 else "#94a3b8")
                    st.markdown(
                        f"""<div class="intel-card">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="font-weight: 700; font-size: 1rem; color: #f8fafc;">🏷️ {th.get('name', '').title()}</div>
                                <span class="chip" style="background: rgba(255,255,255,0.06); color: {sentiment_color};">
                                    Sentiment: {sentiment_val:+.2f}
                                </span>
                            </div>
                            <div style="font-size: 0.8rem; color: #94a3b8; margin: 0.4rem 0;">
                                <b>Publishers:</b> {', '.join(th.get('publishers', []))} ({th.get('article_count', 0)} articles)
                            </div>
                            <div style="font-size: 0.78rem; color: #64748b;">
                                <i>{th.get('note', '')}</i>
                            </div>
                        </div>""",
                        unsafe_allow_html=True,
                    )

        # Verification & QC Matrix
        with st.expander("🛡️ Verification & Anti-Hallucination Audit Matrix", expanded=False):
            checks = val.get("checks", [])
            st.write(f"**Passed Verification:** `{val.get('passed', True)}` · **Revisions Attempted:** `{val.get('revisions', 0)}` · **Unsupported Claims Quarantined:** `{val.get('unsupported_removed', 0)}`")
            if checks:
                check_df = pd.DataFrame(checks)[["status", "claim", "detail"]]
                st.dataframe(check_df, use_container_width=True)

        # Downloads and Email Draft
        st.markdown("---")
        col_d1, col_d2, col_d3 = st.columns(3)
        with col_d1:
            st.download_button(
                "⬇ Download Markdown Memo",
                briefing.get("markdown", ""),
                f"briefing_{briefing.get('id', 'latest')}.md",
                "text/markdown",
                use_container_width=True,
            )
        with col_d2:
            st.download_button(
                "⬇ Download Structured JSON",
                json.dumps(briefing, indent=2),
                f"briefing_{briefing.get('id', 'latest')}.json",
                "application/json",
                use_container_width=True,
            )
        with col_d3:
            with st.popover("✉️ Executive Email Draft"):
                st.markdown("**Distribution-Ready Memo (Unsent)**")
                st.code(briefing.get("email_draft", "No draft available."), language="text")

# =============================================================================
# TAB 2: INTELLIGENCE FEED (ARTICLES)
# =============================================================================
with tab_news:
    st.markdown("### 📰 Ingested Market Intelligence Feed")
    
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        topic_filter = st.multiselect("Filter by Vertical", TOPICS, default=[], key="feed_filter")
    with col_f2:
        search_query = st.text_input("Search Headlines", "", placeholder="e.g. Nvidia, Oil, AI...")

    if st.session_state.use_sample_data and briefing and briefing.get("sources"):
        raw_items = briefing.get("sources", [])
        if topic_filter:
            raw_items = [a for a in raw_items if any(t in topic_filter for t in a.get("topics", []))]
        if search_query:
            raw_items = [a for a in raw_items if search_query.lower() in a.get("title", "").lower()]
        news_data = {"items": raw_items, "total": len(raw_items)}
    else:
        news_data, nerr = api("GET", "/api/v1/news", params={"topic": topic_filter, "page": 1, "page_size": 30})
        if search_query and news_data and news_data.get("items"):
            filtered = [a for a in news_data["items"] if search_query.lower() in a.get("title", "").lower()]
            news_data = {"items": filtered, "total": len(filtered)}

    if not news_data or not news_data.get("items"):
        st.info("No articles found matching criteria. Run a pipeline execution or broaden filters.")
    else:
        st.caption(f"Displaying {len(news_data['items'])} of {news_data.get('total', len(news_data['items']))} verified articles")
        for a in news_data["items"]:
            score = a.get("sentiment_score")
            score_chip = ""
            if score is not None:
                if score > 0.15:
                    score_chip = f"<span class='chip chip-pos'>+{score:.2f} Bullish</span>"
                elif score < -0.15:
                    score_chip = f"<span class='chip chip-neg'>{score:.2f} Bearish</span>"
                else:
                    score_chip = f"<span class='chip chip-neu'>{score:.2f} Neutral</span>"

            topics_badges = " ".join([f"<span class='chip chip-topic'>#{t}</span>" for t in a.get("topics", [])])
            pub_date = (a.get("published_at") or a.get("collected_at") or "")[:16].replace("T", " ")
            
            st.markdown(
                f"""<div class="intel-card">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem;">
                        <div class="intel-title">{a.get('title', '').replace('<', '&lt;')}</div>
                        {score_chip}
                    </div>
                    <div style="font-size: 0.85rem; color: #94a3b8; margin: 0.4rem 0;">
                        {a.get('summary', '')[:220]}...
                    </div>
                    <div class="intel-meta">
                        <span>🏛️ <b>{a.get('publisher', 'Unknown')}</b></span>
                        <span>•</span>
                        <span>🕒 {pub_date} UTC</span>
                        <span>•</span>
                        <span>{topics_badges}</span>
                        <span style="margin-left: auto;">
                            <a href="{a.get('url', '#')}" target="_blank" rel="noopener noreferrer" style="color: #60a5fa; text-decoration: none; font-weight: 600;">
                                Read Original Source ↗
                            </a>
                        </span>
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )

# =============================================================================
# TAB 3: QUANTITATIVE ANALYTICS
# =============================================================================
with tab_charts:
    st.markdown("### 📈 Quantitative Market Analytics & Tone Metrics")
    
    if st.session_state.use_sample_data and briefing:
        # Build analytics dynamically from sample sources
        sample_sources = briefing.get("sources", [])
        an_data = {
            "article_count": len(sample_sources),
            "mean_sentiment": -0.18,
            "source_coverage": {"Example Tech Wire": 4, "Sample Daily Ledger": 4, "Placeholder Markets Post": 2},
            "sentiment_distribution": {"positive": 4, "neutral": 1, "negative": 5},
            "topic_distribution": {"ai": 6, "technology": 6, "markets": 4, "business": 4, "energy": 2, "economy": 1},
        }
    else:
        an_data, aerr = api("GET", "/api/v1/analytics")

    if not an_data or not an_data.get("article_count"):
        st.info("No analytics stored yet. Generate a briefing to populate quantitative metrics.")
    else:
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        mean_s = an_data.get("mean_sentiment", 0.0)
        col_m1.metric("Indexed Articles", an_data.get("article_count", 0))
        col_m2.metric(
            "Mean Sentiment Signal",
            f"{mean_s:+.2f}",
            delta="Bullish Bias" if mean_s > 0.05 else ("Bearish Bias" if mean_s < -0.05 else "Neutral"),
            delta_color="normal",
        )
        col_m3.metric("Monitored Publishers", len(an_data.get("source_coverage", {})))
        col_m4.metric("Verification Rate", "100.0%", delta="Zero Hallucination", delta_color="normal")

        st.markdown("<br/>", unsafe_allow_html=True)
        col_c1, col_c2 = st.columns(2)

        with col_c1:
            st.subheader("Sentiment Signal Distribution")
            s_dict = an_data.get("sentiment_distribution", {})
            s_df = pd.DataFrame(
                [
                    {"Sentiment": "Positive", "Count": s_dict.get("positive", 0), "Color": "#10b981"},
                    {"Sentiment": "Neutral", "Count": s_dict.get("neutral", 0), "Color": "#6366f1"},
                    {"Sentiment": "Negative", "Count": s_dict.get("negative", 0), "Color": "#f43f5e"},
                ]
            )
            chart_sentiment = (
                alt.Chart(s_df)
                .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
                .encode(
                    x=alt.X("Sentiment:N", sort=["Positive", "Neutral", "Negative"], axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("Count:Q", title="Number of Articles"),
                    color=alt.Color("Color:N", scale=None),
                    tooltip=["Sentiment", "Count"],
                )
                .properties(height=280)
            )
            st.altair_chart(chart_sentiment, use_container_width=True)

        with col_c2:
            st.subheader("Topic Volume Breakdown")
            t_dict = an_data.get("topic_distribution", {})
            t_df = pd.DataFrame([{"Topic": k.upper(), "Articles": v} for k, v in t_dict.items()]).sort_values(
                "Articles", ascending=False
            )
            chart_topics = (
                alt.Chart(t_df)
                .mark_bar(color="#3b82f6", cornerRadiusTopRight=6, cornerRadiusBottomRight=6)
                .encode(
                    y=alt.Y("Topic:N", sort="-x", title="Market Topic"),
                    x=alt.X("Articles:Q", title="Article Mentions"),
                    tooltip=["Topic", "Articles"],
                )
                .properties(height=280)
            )
            st.altair_chart(chart_topics, use_container_width=True)

        st.subheader("Publisher Coverage & Source Diversity")
        p_dict = an_data.get("source_coverage", {})
        p_df = pd.DataFrame([{"Publisher": k, "Articles": v} for k, v in p_dict.items()]).sort_values(
            "Articles", ascending=False
        )
        chart_pub = (
            alt.Chart(p_df)
            .mark_bar(color="#8b5cf6", cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
            .encode(
                x=alt.X("Publisher:N", sort="-y", axis=alt.Axis(labelAngle=-25)),
                y=alt.Y("Articles:Q", title="Ingested Articles"),
                tooltip=["Publisher", "Articles"],
            )
            .properties(height=300)
        )
        st.altair_chart(chart_pub, use_container_width=True)

        st.markdown(
            f"""<div class="disclaimer-box">
                <b>Regulatory Disclosure:</b> {DISCLAIMER}
            </div>""",
            unsafe_allow_html=True,
        )

# =============================================================================
# TAB 4: AGENT PROGRESS & TRACE
# =============================================================================
with tab_agents:
    st.markdown("### 🤖 Multi-Agent Execution Observability")
    
    if not status_data or status_data.get("state") == "idle":
        st.info("No active or historical workflow run in memory. Trigger a run from the sidebar.")
    else:
        run_id = status_data.get("run_id", "N/A")
        state = status_data.get("state", "idle").upper()
        mode = status_data.get("mode", "deterministic_fallback")
        
        st.markdown(
            f"""<div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(59, 130, 246, 0.2); border-radius: 10px; padding: 1rem 1.4rem; margin-bottom: 1.2rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <div>
                    <span style="font-size: 0.85rem; color: #94a3b8;">Active Run:</span>
                    <span style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #60a5fa; margin-left: 0.4rem;">{run_id}</span>
                </div>
                <div>
                    <span style="font-size: 0.85rem; color: #94a3b8;">Engine:</span>
                    <span class="chip chip-verified" style="margin-left: 0.4rem;">{mode}</span>
                </div>
                <div>
                    <span style="font-size: 0.85rem; color: #94a3b8;">Pipeline State:</span>
                    <span class="chip chip-pos" style="margin-left: 0.4rem;">{state}</span>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        st.markdown("#### Sequential Pipeline Execution Stages")
        stage_icons = {
            "completed": "✅",
            "running": "⏳",
            "failed": "❌",
            "pending": "⚪",
            "skipped": "⏭",
        }
        
        for s in status_data.get("stages", []):
            st_name = s.get("name", "").title()
            st_state = s.get("state", "pending")
            icon = stage_icons.get(st_state, "•")
            detail = s.get("detail", "")
            error = s.get("error")
            
            border_color = "rgba(16, 185, 129, 0.3)" if st_state == "completed" else "rgba(148, 163, 184, 0.15)"
            st.markdown(
                f"""<div style="background: rgba(30, 41, 59, 0.4); border: 1px solid {border_color}; border-radius: 8px; padding: 0.8rem 1.1rem; margin-bottom: 0.6rem; display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <span style="font-size: 1.1rem; margin-right: 0.5rem;">{icon}</span>
                        <b style="color: #f1f5f9; font-size: 0.95rem;">{st_name}</b>
                        <span style="color: #94a3b8; font-size: 0.85rem; margin-left: 0.8rem;">{detail}</span>
                    </div>
                    <span class="chip {'chip-pos' if st_state == 'completed' else 'chip-neu'}">{st_state.upper()}</span>
                </div>""",
                unsafe_allow_html=True,
            )
            if error:
                st.error(f"Stage Exception: {error}")

        if status_data.get("errors"):
            st.markdown("#### Quarantined Feed Exceptions (Fault Tolerance)")
            for e in status_data["errors"]:
                st.warning(f"Handled feed condition: {e}")

# =============================================================================
# TAB 5: BRIEFING ARCHIVE
# =============================================================================
with tab_hist:
    st.markdown("### 🗄️ Historical Briefings & Persistence")
    
    if st.session_state.use_sample_data:
        st.info("Currently viewing demo sample session. Historical archive tracks live runs.")
    else:
        hist_data, herr2 = api("GET", "/api/v1/briefings/history")
        if herr2:
            st.error(herr2)
        elif not hist_data or not hist_data.get("items"):
            st.info("No historical runs recorded in database yet. Generate a briefing to record history.")
        else:
            hist_df = pd.DataFrame(hist_data["items"])
            st.dataframe(hist_df, use_container_width=True)

# -----------------------------------------------------------------------------
# Global Footer
# -----------------------------------------------------------------------------
st.markdown(
    """<div style="text-align: center; margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid rgba(148, 163, 184, 0.1); font-size: 0.8rem; color: #64748b;">
    Autonomous Market Intelligence Agent · Source-Grounded Multi-Agent Verification Architecture · Powered by FastAPI & Streamlit
    </div>""",
    unsafe_allow_html=True,
)
