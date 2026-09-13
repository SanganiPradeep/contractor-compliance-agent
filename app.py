"""
app.py
--------------------------------------------------------------------------
Professional Streamlit web UI for ComplianceScout.

Provides a visual chat interface for contractors to interact with the
ComplianceScout Strands Agent instead of using the terminal CLI. Designed
for the "Professional Agents" hackathon track with a clean contractor/
compliance dashboard aesthetic (slate/navy/orange accent palette).

Launch:
    streamlit run app.py
--------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import re
import uuid

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent.compliance_agent import build_agent  # noqa: E402

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ComplianceScout — Contractor Compliance Dashboard",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — slate/navy/orange "Professional Agents" theme
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
/* ---------- Google Fonts ---------- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ---------- Root variables ---------- */
:root {
    --navy:        #0f1b2d;
    --navy-light:  #162236;
    --slate:       #1e293b;
    --slate-mid:   #334155;
    --slate-light: #475569;
    --orange:      #f97316;
    --orange-glow: #fb923c;
    --surface:     #1e293b;
    --text:        #e2e8f0;
    --text-muted:  #94a3b8;
    --success:     #22c55e;
    --warning:     #eab308;
    --danger:      #ef4444;
    --radius:      0.75rem;
}

/* ---------- Global overrides ---------- */
html, body, [class*="css"] {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
}
.stApp {
    background: linear-gradient(165deg, var(--navy) 0%, #0c1220 100%);
}

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {
    background: var(--navy-light) !important;
    border-right: 1px solid rgba(249, 115, 22, 0.15);
}
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: var(--orange) !important;
}
section[data-testid="stSidebar"] label {
    color: var(--text-muted) !important;
    font-weight: 500;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    font-size: 0.7rem !important;
}

/* ---------- Text inputs ---------- */
.stTextInput input {
    background: var(--slate) !important;
    border: 1px solid var(--slate-mid) !important;
    color: var(--text) !important;
    border-radius: var(--radius) !important;
    transition: border-color 0.2s ease;
}
.stTextInput input:focus {
    border-color: var(--orange) !important;
    box-shadow: 0 0 0 2px rgba(249, 115, 22, 0.18) !important;
}

/* ---------- Buttons ---------- */
.stButton > button {
    background: linear-gradient(135deg, var(--orange) 0%, #ea580c 100%) !important;
    color: #fff !important;
    border: none !important;
    border-radius: var(--radius) !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em;
    padding: 0.55rem 1.25rem !important;
    transition: transform 0.15s ease, box-shadow 0.2s ease;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(249, 115, 22, 0.35) !important;
}
.stButton > button:active {
    transform: translateY(0);
}

/* ---------- Chat messages ---------- */
[data-testid="stChatMessage"] {
    background: var(--surface) !important;
    border: 1px solid var(--slate-mid) !important;
    border-radius: var(--radius) !important;
    padding: 1rem 1.25rem !important;
    margin-bottom: 0.65rem;
}

/* ---------- Chat input ---------- */
[data-testid="stChatInput"] textarea {
    background: var(--slate) !important;
    border: 1px solid var(--slate-mid) !important;
    color: var(--text) !important;
    border-radius: var(--radius) !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: var(--orange) !important;
    box-shadow: 0 0 0 2px rgba(249, 115, 22, 0.18) !important;
}

/* ---------- Permit-draft container ---------- */
.permit-draft-container {
    background: linear-gradient(135deg, rgba(30, 41, 59, 0.95), rgba(15, 27, 45, 0.97));
    border: 1px solid var(--slate-mid);
    border-left: 4px solid var(--orange);
    border-radius: var(--radius);
    padding: 1.5rem;
    margin: 1rem 0;
    position: relative;
    overflow: hidden;
}
.permit-draft-container::before {
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 120px; height: 120px;
    background: radial-gradient(circle, rgba(249,115,22,0.06) 0%, transparent 70%);
    pointer-events: none;
}

/* ---------- Draft badge ---------- */
.draft-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: linear-gradient(135deg, rgba(234, 179, 8, 0.15), rgba(249, 115, 22, 0.12));
    border: 1px solid rgba(234, 179, 8, 0.35);
    color: #fbbf24;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 0.35rem 0.85rem;
    border-radius: 99px;
    margin-bottom: 1rem;
    animation: pulse-badge 2.5s ease-in-out infinite;
}
@keyframes pulse-badge {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.72; }
}

/* ---------- Header area ---------- */
.scout-header {
    padding: 1.25rem 0 0.75rem 0;
}
.scout-header h1 {
    font-size: 1.6rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, var(--orange) 0%, var(--orange-glow) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0;
}
.scout-header p {
    color: var(--text-muted);
    font-size: 0.85rem;
    margin-top: 0.25rem;
}

/* ---------- Metric cards ---------- */
.metric-card {
    background: var(--surface);
    border: 1px solid var(--slate-mid);
    border-radius: var(--radius);
    padding: 0.85rem 1rem;
    text-align: center;
}
.metric-card .metric-value {
    font-size: 1.35rem;
    font-weight: 700;
    color: var(--orange);
}
.metric-card .metric-label {
    font-size: 0.68rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-top: 0.15rem;
}

/* ---------- Divider ---------- */
.sidebar-divider {
    border: none;
    border-top: 1px solid rgba(249, 115, 22, 0.12);
    margin: 1.25rem 0;
}

/* ---------- Status indicator ---------- */
.status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--success);
    margin-right: 0.4rem;
    animation: blink 2s ease-in-out infinite;
}
@keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

/* ---------- Scrollbar ---------- */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--navy); }
::-webkit-scrollbar-thumb { background: var(--slate-mid); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--orange); }

/* ---------- Hide default Streamlit chrome ---------- */
#MainMenu, footer, header { visibility: hidden; }
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = f"web-{uuid.uuid4().hex[:8]}"
if "agent" not in st.session_state:
    st.session_state.agent = None
if "turn_count" not in st.session_state:
    st.session_state.turn_count = 0
if "permits_drafted" not in st.session_state:
    st.session_state.permits_drafted = 0


def _ensure_agent() -> None:
    """Lazily build or rebuild the agent when session parameters change."""
    sid = st.session_state.session_id
    if st.session_state.agent is None or st.session_state.get("_agent_sid") != sid:
        st.session_state.agent = build_agent(session_id=sid)
        st.session_state._agent_sid = sid


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        '<div class="scout-header">'
        "<h1>🏗️ ComplianceScout</h1>"
        "<p>Contractor Compliance Dashboard</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    st.markdown("##### Agent Controls")

    license_num = st.text_input(
        "Contractor License #",
        value="",
        placeholder="e.g. CA-B-123456",
        key="license_input",
    )
    default_zip = st.text_input(
        "Default ZIP Code",
        value="",
        placeholder="e.g. 94103",
        key="zip_input",
    )
    session_id_input = st.text_input(
        "Session ID",
        value=st.session_state.session_id,
        key="session_input",
    )
    # Sync session ID if the user changed it
    if session_id_input and session_id_input != st.session_state.session_id:
        st.session_state.session_id = session_id_input

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    # Metrics
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f'<div class="metric-card">'
            f'<div class="metric-value">{st.session_state.turn_count}</div>'
            f'<div class="metric-label">Turns</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f'<div class="metric-card">'
            f'<div class="metric-value">{st.session_state.permits_drafted}</div>'
            f'<div class="metric-label">Permits Drafted</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    # Action buttons
    if st.button("🔍  View AgentCore Traces", use_container_width=True):
        st.info(
            "Run `agentcore obs` in your terminal or open the **CloudWatch GenAI "
            "Observability** console to view full OpenTelemetry trace spans for "
            "every model invocation and tool call logged by ComplianceTraceHooks.",
            icon="📡",
        )

    if st.button("🗑️  Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.session_state.agent = None
        st.session_state.turn_count = 0
        st.session_state.permits_drafted = 0
        st.rerun()

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    # Connection status
    st.markdown(
        '<span class="status-dot"></span>'
        '<span style="color: var(--text-muted); font-size: 0.78rem;">'
        "Agent Online — Bedrock Connected</span>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_PERMIT_DRAFT_RE = re.compile(
    r"(#\s*Permit Application Draft.*?)(?=\n---\s*$|\Z)",
    re.DOTALL | re.MULTILINE,
)

_DRAFT_STATUS_RE = re.compile(
    r"\*\*STATUS:\s*DRAFT\b.*?\*\*",
    re.IGNORECASE,
)


def _contains_permit_draft(text: str) -> bool:
    """Return True if the text contains a drafted permit document."""
    return bool(_PERMIT_DRAFT_RE.search(text))


def _render_permit_draft(md_block: str) -> None:
    """Render a permit-draft markdown block inside a styled container."""
    st.markdown(
        '<div class="permit-draft-container">'
        '<div class="draft-badge">⚠️ STATUS: DRAFT — REQUIRES HUMAN SIGNATURE</div>',
        unsafe_allow_html=True,
    )
    st.markdown(md_block)
    st.markdown("</div>", unsafe_allow_html=True)


def _render_assistant_message(text: str) -> None:
    """Render an assistant message, extracting permit drafts into styled cards."""
    match = _PERMIT_DRAFT_RE.search(text)
    if match:
        before = text[: match.start()].strip()
        draft_md = match.group(1).strip()
        after = text[match.end() :].strip()

        if before:
            st.markdown(before)
        _render_permit_draft(draft_md)
        if after:
            # Strip the bare STATUS line from after-text since we rendered the badge
            after_cleaned = _DRAFT_STATUS_RE.sub("", after).strip()
            if after_cleaned:
                st.markdown(after_cleaned)
    else:
        st.markdown(text)


# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------
st.markdown(
    '<div class="scout-header">'
    "<h1>ComplianceScout</h1>"
    "<p>Your autonomous compliance assistant — describe your project and let Scout handle the codes &amp; permits.</p>"
    "</div>",
    unsafe_allow_html=True,
)

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🏗️" if msg["role"] == "user" else "🛡️"):
        if msg["role"] == "assistant":
            _render_assistant_message(msg["content"])
        else:
            st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Describe your project or ask a compliance question…"):
    # Prepend context from sidebar if provided
    context_prefix = ""
    if license_num:
        context_prefix += f"[Contractor License: {license_num}] "
    if default_zip:
        context_prefix += f"[Default ZIP: {default_zip}] "

    full_prompt = f"{context_prefix}{prompt}" if context_prefix else prompt

    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🏗️"):
        st.markdown(prompt)

    # Invoke agent
    _ensure_agent()
    with st.chat_message("assistant", avatar="🛡️"):
        with st.spinner("Researching codes & drafting…"):
            try:
                result = st.session_state.agent(full_prompt)
                response_text = str(result)
            except Exception as exc:
                response_text = (
                    f"⚠️ **ComplianceScout encountered an error:**\n\n"
                    f"```\n{exc}\n```\n\n"
                    f"Please check your AWS credentials and Bedrock model access."
                )

        _render_assistant_message(response_text)

    st.session_state.messages.append({"role": "assistant", "content": response_text})
    st.session_state.turn_count += 1

    # Track permit drafts
    if _contains_permit_draft(response_text):
        st.session_state.permits_drafted += 1

    st.rerun()
