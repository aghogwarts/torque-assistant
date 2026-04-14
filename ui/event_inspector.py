"""
event_inspector.py — Page 3: Event Inspector

Pick any event from the CSV, run it live through the workflow,
and see the step-by-step breakdown: validation, RAG chunks retrieved,
agent reasoning, and tool called.
"""

import pandas as pd
import streamlit as st

from core.loader import event_from_row
from main import run_event_detailed, build_state
from ui.styles import inject_css, validation_badge, severity_badge, action_badge


def render(resources: dict):
    inject_css()

    df          = resources["df"]
    workflow    = resources["workflow"]
    spec_lookup = resources["spec_lookup"]

    st.markdown('<div class="section-header">Event Inspector</div>',
                unsafe_allow_html=True)
    st.caption("Pick any event, run it live, and step through exactly what the workflow did.")

    # ── Event picker ──────────────────────────────────────────────────────────
    col1, col2 = st.columns([2, 1])
    with col1:
        search = st.text_input("Search Event ID", placeholder="EVT-0000...")
    with col2:
        joint_filter = st.selectbox(
            "Filter by Joint",
            ["All"] + sorted(df["joint"].unique().tolist()),
        )

    filtered_df = df.copy()
    if search:
        filtered_df = filtered_df[filtered_df["event_id"].str.contains(search, case=False)]
    if joint_filter != "All":
        filtered_df = filtered_df[filtered_df["joint"] == joint_filter]

    if filtered_df.empty:
        st.warning("No events match your filters.")
        return

    selected_id = st.selectbox(
        "Select Event",
        filtered_df["event_id"].tolist(),
        help="Select an event to inspect.",
    )

    row        = df[df["event_id"] == selected_id].iloc[0]
    event      = event_from_row(row)
    sc_value   = spec_lookup.get(event.joint)

    # ── Event summary card ────────────────────────────────────────────────────
    st.markdown('<div class="section-header" style="margin-top:1rem;">Event Details</div>',
                unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Event ID",        selected_id)
    c2.metric("Joint",           event.joint)
    c3.metric("Vehicle Model",   row.get("vehicle_model", "—"))
    c4.metric("Tool",            row.get("tool_id", "—"))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Target Torque",   f"{event.target_torque_nm} Nm")
    c6.metric("Actual Torque",   f"{event.actual_torque_nm} Nm")
    c7.metric("Tolerance",       f"±{event.tolerance_nm} Nm")
    c8.metric("Safety Critical", str(sc_value) if sc_value is not None else "UNKNOWN")

    angle_info = (f"{event.angle_required}°  required / "
                  f"{event.actual_angle_deg or 'not recorded'}° actual"
                  if event.angle_required else "Not required")
    st.caption(f"Angle: {angle_info}  |  Timestamp: {row.get('timestamp', '—')}")

    st.divider()

    # ── Run button ────────────────────────────────────────────────────────────
    if st.button("Run This Event", type="primary"):
        st.session_state["inspector_steps"] = None
        st.session_state["inspector_error"] = None
        st.session_state["inspector_event"] = selected_id

        with st.spinner("Running event through workflow..."):
            steps, error = run_event_detailed(workflow, event, spec_lookup)

        st.session_state["inspector_steps"] = steps
        st.session_state["inspector_error"] = error

    # ── Step-by-step results ──────────────────────────────────────────────────
    if st.session_state.get("inspector_event") == selected_id:
        steps = st.session_state.get("inspector_steps")
        error = st.session_state.get("inspector_error")

        if error and not steps:
            st.markdown(
                f'<div class="error-card">Run failed: {error}</div>',
                unsafe_allow_html=True,
            )
            return

        if steps:
            st.markdown('<div class="section-header">Step-by-Step Breakdown</div>',
                        unsafe_allow_html=True)
            _render_steps(steps)

            if error:
                st.markdown(
                    f'<div class="error-card">Run ended with error: {error}</div>',
                    unsafe_allow_html=True,
                )


# ── Step renderers ────────────────────────────────────────────────────────────

def _render_steps(steps: list):
    for step in steps:
        node  = step["node"]
        state = step["state"]
        _render_node(node, state)


def _render_node(node: str, state: dict):
    node_labels = {
        "validate":     "1. Validation",
        "auto_close":   "2. Auto-Close (fast path)",
        "trend":        "2. Trend Detection (SPC)",
        "rag":          "3. SOP Retrieval",
        "rag_incidents":"4. Incident History Retrieval",
        "agent":        "5. Decision Agent",
        "finalize":     "6. Finalize Action",
    }
    label = node_labels.get(node, node.upper())

    with st.expander(label, expanded=True):
        if node == "validate":
            _render_validate(state)
        elif node == "auto_close":
            _render_auto_close(state)
        elif node == "trend":
            _render_trend(state)
        elif node == "rag":
            _render_rag(state)
        elif node == "rag_incidents":
            _render_rag_incidents(state)
        elif node == "agent":
            _render_agent(state)
        elif node == "finalize":
            _render_finalize(state)


def _render_validate(state: dict):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Validation Result**")
        v = state.get("validation", "—")
        st.markdown(
            f'<div style="font-size:1.1rem; margin-top:0.25rem;">'
            f'{_validation_badge_html(v)}</div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown("**Severity**")
        s = state.get("severity", "—")
        st.markdown(
            f'<div style="font-size:1.1rem; margin-top:0.25rem;">'
            f'{_severity_badge_html(s)}</div>',
            unsafe_allow_html=True,
        )
    target = state.get("target_torque_nm", 0)
    actual = state.get("actual_torque_nm", 0)
    tol    = state.get("tolerance_nm", 0)
    dev    = actual - target
    dev_pct = (dev / target * 100) if target else 0
    st.caption(
        f"Target: {target} Nm  |  Actual: {actual} Nm  |  "
        f"Tolerance: ±{tol} Nm  |  Deviation: {dev:+.2f} Nm ({dev_pct:+.1f}%)"
    )


def _render_auto_close(state: dict):
    st.markdown(
        '<div class="info-card">Fast path taken — validation is OK on a '
        'non-safety-critical joint. No RAG retrieval or LLM call needed.</div>',
        unsafe_allow_html=True,
    )
    result = state.get("agent_result") or {}
    action = result.get("status", "—")
    st.markdown(f"**Action:** {_action_badge_html(action)}", unsafe_allow_html=True)


def _render_trend(state: dict):
    """Render trend detection / SPC output."""
    trend = state.get("trend_context", "")
    if not trend:
        st.markdown("No trend data available.")
        return

    is_alert = "TREND ALERT" in trend or "NOT CAPABLE" in trend or "Warning" in trend
    if is_alert:
        st.markdown(
            f'<div class="info-card" style="border-left: 4px solid #e74c3c; white-space: pre-wrap;">'
            f'{trend}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="info-card" style="white-space: pre-wrap;">{trend}</div>',
            unsafe_allow_html=True,
        )


def _render_rag(state: dict):
    chunks = state.get("rag_context", [])
    st.markdown(f"**{len(chunks)} SOP chunks retrieved**")
    for i, chunk in enumerate(chunks, 1):
        st.markdown(f"*Chunk {i}:*")
        st.code(chunk, language=None)


def _render_rag_incidents(state: dict):
    incidents = state.get("incident_context", [])
    st.markdown(f"**{len(incidents)} past incident(s) retrieved**")
    for i, inc in enumerate(incidents, 1):
        st.markdown(f"*Incident {i}:*")
        st.code(inc, language=None)


def _render_agent(state: dict):
    """Render the v2 structured agent decision with all fields."""
    decision = state.get("agent_decision") or {}
    result = state.get("agent_result") or {}
    action = result.get("status", "—")
    reasoning = decision.get("reasoning") or state.get("agent_reasoning", "")
    severity = decision.get("severity", "")
    confidence = decision.get("confidence")

    # ── Decision + Severity + Confidence row ──────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Decision**")
        st.markdown(f"{_action_badge_html(action)}", unsafe_allow_html=True)

    with col2:
        st.markdown("**Agent Severity**")
        if severity:
            st.markdown(f"{_severity_badge_html(severity)}", unsafe_allow_html=True)
        else:
            st.markdown("`—`")

    with col3:
        st.markdown("**Confidence**")
        if confidence is not None:
            pct = f"{confidence:.0%}"
            color = "#e74c3c" if confidence < 0.90 else "#27ae60"
            flag = " ⚠ Needs Review" if confidence < 0.90 else ""
            st.markdown(
                f'<span style="color:{color}; font-weight:600;">{pct}</span>'
                f'<span style="color:#e74c3c; font-size:0.85rem;">{flag}</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown("`—`")

    # ── Reasoning ─────────────────────────────────────────────────────────
    if reasoning:
        st.markdown("**Agent Reasoning**")
        st.markdown(
            f'<div class="info-card" style="white-space: pre-wrap;">'
            f'{reasoning}</div>',
            unsafe_allow_html=True,
        )

    # ── Root Cause + Recommended Corrective ───────────────────────────────
    root_cause = decision.get("root_cause_hypothesis", "")
    corrective = decision.get("recommended_corrective", "")

    if root_cause and root_cause != "N/A":
        st.markdown("**Root Cause Hypothesis**")
        st.markdown(
            f'<div class="info-card">{root_cause}</div>',
            unsafe_allow_html=True,
        )

    if corrective and corrective != "N/A":
        st.markdown("**Recommended Corrective Action**")
        st.markdown(
            f'<div class="info-card">{corrective}</div>',
            unsafe_allow_html=True,
        )

    # ── SOP References ────────────────────────────────────────────────────
    sop_refs = decision.get("sop_references", [])
    if sop_refs:
        st.markdown("**SOP References**")
        for ref in sop_refs:
            st.markdown(f"- `{ref}`")

    # ── Safety Critical ───────────────────────────────────────────────────
    sc = state.get("safety_critical")
    label = "Yes" if sc is True else ("No" if sc is False else "Unknown")
    st.caption(f"Safety-Critical Joint: {label}")


def _render_finalize(state: dict):
    """Render the finalize step — shows which tool was executed."""
    result = state.get("agent_result") or {}
    action = result.get("status", "—")
    st.markdown(f"**Executed Action:** {_action_badge_html(action)}", unsafe_allow_html=True)
    st.caption("The finalize node executed the tool call based on the agent's decision above.")


# ── Badge HTML helpers (inline, no extra import) ──────────────────────────────

def _validation_badge_html(result: str) -> str:
    cls_map = {
        "OK": "badge-ok", "OVER_TORQUE": "badge-over",
        "UNDER_TORQUE": "badge-under", "ANGLE_MISSING": "badge-angle",
    }
    cls = cls_map.get(result, "badge-low")
    return f'<span class="badge {cls}">{result}</span>'


def _severity_badge_html(severity: str) -> str:
    cls_map = {"LOW": "badge-low", "MEDIUM": "badge-medium", "HIGH": "badge-high"}
    cls = cls_map.get(severity, "badge-low")
    return f'<span class="badge {cls}">{severity}</span>'


def _action_badge_html(action: str) -> str:
    cls_map = {
        "CLOSED": "badge-closed",
        "REWORK_LOGGED": "badge-rework",
        "ESCALATED": "badge-escalated",
    }
    cls = cls_map.get(action, "badge-low")
    label = action.replace("_", " ")
    return f'<span class="badge {cls}">{label}</span>'