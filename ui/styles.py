"""
styles.py
Shared CSS injected into every page and Plotly chart theme constants.
Industrial dark aesthetic — amber accents, monospace data display.
"""

# ── Status colours (used in charts and badges) ────────────────────────────────

STATUS_COLORS = {
    "OK":            "#22c55e",
    "OVER_TORQUE":   "#ef4444",
    "UNDER_TORQUE":  "#f97316",
    "ANGLE_MISSING": "#eab308",
    "ERROR":         "#6b7280",
}

SEVERITY_COLORS = {
    "LOW":    "#6b7280",
    "MEDIUM": "#f97316",
    "HIGH":   "#ef4444",
}

ACTION_COLORS = {
    "CLOSED":       "#22c55e",
    "REWORK_LOGGED":"#f97316",
    "ESCALATED":    "#ef4444",
    "ERROR":        "#6b7280",
}

ROUTE_COLORS = {
    "auto_close": "#3b82f6",
    "full_path":  "#8b5cf6",
}

# ── Plotly chart theme ────────────────────────────────────────────────────────

PLOTLY_LAYOUT = dict(
    paper_bgcolor="#13161e",
    plot_bgcolor="#13161e",
    font=dict(color="#e2e8f0", family="IBM Plex Mono, monospace", size=11),
    title_font=dict(color="#f59e0b", size=13),
    xaxis=dict(gridcolor="#1e2330", linecolor="#2d3348", tickfont=dict(size=10)),
    yaxis=dict(gridcolor="#1e2330", linecolor="#2d3348", tickfont=dict(size=10)),
    legend=dict(bgcolor="#1a1e29", bordercolor="#2d3348", borderwidth=1),
    margin=dict(l=16, r=16, t=40, b=16),
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

/* Sidebar nav styling */
[data-testid="stSidebarNav"] { padding-top: 0.5rem; }

/* Metric cards */
[data-testid="stMetric"] {
    background: #13161e;
    border: 1px solid #2d3348;
    border-radius: 6px;
    padding: 0.75rem 1rem;
}
[data-testid="stMetricLabel"] { color: #8892a4 !important; font-size: 0.75rem; }
[data-testid="stMetricValue"] { color: #f59e0b !important; font-size: 1.4rem; font-weight: 600; }
[data-testid="stMetricDelta"] { font-size: 0.75rem; }

/* Dataframe */
[data-testid="stDataFrame"] { border: 1px solid #2d3348; border-radius: 6px; }

/* Expander */
[data-testid="stExpander"] {
    border: 1px solid #2d3348 !important;
    border-radius: 6px !important;
    background: #13161e !important;
}

/* Status badge helper classes */
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 600;
    font-family: 'IBM Plex Mono', monospace;
    letter-spacing: 0.03em;
}
.badge-ok         { background: #14532d; color: #22c55e; }
.badge-over       { background: #450a0a; color: #ef4444; }
.badge-under      { background: #431407; color: #f97316; }
.badge-angle      { background: #422006; color: #eab308; }
.badge-low        { background: #1c1c1c; color: #6b7280; }
.badge-medium     { background: #431407; color: #f97316; }
.badge-high       { background: #450a0a; color: #ef4444; }
.badge-closed     { background: #14532d; color: #22c55e; }
.badge-rework     { background: #431407; color: #f97316; }
.badge-escalated  { background: #450a0a; color: #ef4444; }

/* Section header */
.section-header {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    color: #f59e0b;
    text-transform: uppercase;
    border-bottom: 1px solid #2d3348;
    padding-bottom: 0.4rem;
    margin-bottom: 0.75rem;
}

/* Info card */
.info-card {
    background: #13161e;
    border: 1px solid #2d3348;
    border-left: 3px solid #f59e0b;
    border-radius: 6px;
    padding: 0.75rem 1rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
}

/* Warn card */
.warn-card {
    background: #1a1200;
    border: 1px solid #92400e;
    border-left: 3px solid #f59e0b;
    border-radius: 6px;
    padding: 0.75rem 1rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    color: #fcd34d;
}

/* Error card */
.error-card {
    background: #1a0000;
    border: 1px solid #7f1d1d;
    border-left: 3px solid #ef4444;
    border-radius: 6px;
    padding: 0.75rem 1rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    color: #fca5a5;
}

/* Node step card in event inspector */
.node-card {
    background: #13161e;
    border: 1px solid #2d3348;
    border-radius: 6px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.5rem;
}
.node-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    font-weight: 600;
    color: #f59e0b;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.4rem;
}
</style>
"""


def inject_css():
    """Call once per page render to inject the shared CSS."""
    import streamlit as st
    st.markdown(CSS, unsafe_allow_html=True)


def validation_badge(result: str) -> str:
    cls_map = {
        "OK":            "badge-ok",
        "OVER_TORQUE":   "badge-over",
        "UNDER_TORQUE":  "badge-under",
        "ANGLE_MISSING": "badge-angle",
    }
    cls = cls_map.get(result, "badge-low")
    return f'<span class="badge {cls}">{result}</span>'


def severity_badge(severity: str) -> str:
    cls_map = {
        "LOW":    "badge-low",
        "MEDIUM": "badge-medium",
        "HIGH":   "badge-high",
    }
    cls = cls_map.get(severity, "badge-low")
    return f'<span class="badge {cls}">{severity}</span>'


def action_badge(action: str) -> str:
    cls_map = {
        "CLOSED":        "badge-closed",
        "REWORK_LOGGED": "badge-rework",
        "ESCALATED":     "badge-escalated",
    }
    cls = cls_map.get(action, "badge-low")
    label = action.replace("_", " ")
    return f'<span class="badge {cls}">{label}</span>'
