"""
analytics.py — Page 2: Analytics Dashboard

Charts and statistics from the most recent batch run (session state)
or any past run loaded from the run_reports/ directory.
Also includes raw data charts (drift timeline) from the original CSV.
"""

import json
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ui.styles import (
    inject_css, PLOTLY_LAYOUT, STATUS_COLORS,
    SEVERITY_COLORS, ACTION_COLORS,
)


def render(resources: dict):
    inject_css()

    st.markdown('<div class="section-header">Analytics Dashboard</div>',
                unsafe_allow_html=True)

    # ── Data source selector ──────────────────────────────────────────────────
    source = _select_data_source()
    if source is None:
        return

    results, run_log, label = source
    df_raw = resources["df"]  # original CSV for drift timeline

    st.caption(f"Showing: **{label}** — {len(results)} events")
    st.divider()

    # ── Summary metrics row ───────────────────────────────────────────────────
    _render_metrics(results)
    st.divider()

    # ── Charts grid ──────────────────────────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.plotly_chart(_chart_validation(results), use_container_width=True)
        st.plotly_chart(_chart_actions(results, run_log), use_container_width=True)
        st.plotly_chart(_chart_faults_by_joint(results), use_container_width=True)

    with col_right:
        st.plotly_chart(_chart_severity(results), use_container_width=True)
        st.plotly_chart(_chart_routing(results), use_container_width=True)
        st.plotly_chart(_chart_safety_split(results), use_container_width=True)

    st.divider()

    # ── Drift timeline (from raw CSV data) ────────────────────────────────────
    st.markdown('<div class="section-header">Drift Timeline</div>', unsafe_allow_html=True)
    st.caption("Actual vs target torque over time — coloured by validation result. "
               "Drift windows appear as clusters of non-OK points.")
    _render_drift_timeline(df_raw)

    st.divider()

    # ── Full results table ────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Results Table</div>', unsafe_allow_html=True)
    _render_results_table(results)


# ── Data source ───────────────────────────────────────────────────────────────

def _select_data_source():
    """
    Returns (results, run_log, label) from either session state (current run)
    or a past run loaded from run_reports/.
    """
    has_current = bool(st.session_state.get("results"))
    past_runs   = _list_past_runs()

    options = []
    if has_current:
        options.append("Current run")
    if past_runs:
        options += [f"Past: {r}" for r in past_runs]

    if not options:
        st.markdown(
            '<div class="info-card">No run data available yet. '
            'Go to <b>Batch Runner</b> and run a batch first.</div>',
            unsafe_allow_html=True,
        )
        return None

    selected = st.selectbox("Data source", options)

    if selected == "Current run":
        return (
            st.session_state["results"],
            st.session_state.get("run_log", []),
            "Current run",
        )
    else:
        run_label = selected.replace("Past: ", "")
        return _load_past_run(run_label)


def _list_past_runs() -> list[str]:
    reports_dir = "run_reports"
    if not os.path.exists(reports_dir):
        return []
    return sorted(
        [d for d in os.listdir(reports_dir)
         if os.path.isdir(os.path.join(reports_dir, d))],
        reverse=True,
    )


def _load_past_run(label: str):
    path = os.path.join("run_reports", label, "report.json")
    if not os.path.exists(path):
        st.error(f"report.json not found for {label}")
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["events"], data.get("run_log", []), label


# ── Summary metrics ───────────────────────────────────────────────────────────

def _render_metrics(results: list):
    total       = len(results)
    faults      = sum(1 for r in results if r["validation"] and r["validation"] != "OK")
    escalated   = sum(1 for r in results if r["action"] == "ESCALATED")
    reworks     = sum(1 for r in results if r["action"] == "REWORK_LOGGED")
    auto_closed = sum(1 for r in results if "auto_close" in r["path"])
    errors      = sum(1 for r in results if r["error"])

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Events",  total)
    c2.metric("Faults",        faults)
    c3.metric("Escalated",     escalated)
    c4.metric("Rework",        reworks)
    c5.metric("Auto-Closed",   auto_closed)
    c6.metric("Errors",        errors)


# ── Charts ────────────────────────────────────────────────────────────────────

def _chart_validation(results: list) -> go.Figure:
    counts = {}
    for r in results:
        k = r["validation"] or "ERROR"
        counts[k] = counts.get(k, 0) + 1

    fig = go.Figure(go.Pie(
        labels=list(counts.keys()),
        values=list(counts.values()),
        hole=0.55,
        marker_colors=[STATUS_COLORS.get(k, "#6b7280") for k in counts],
        textinfo="label+percent",
        textfont_size=10,
    ))
    fig.update_layout(**PLOTLY_LAYOUT, title="Validation Breakdown")
    return fig


def _chart_severity(results: list) -> go.Figure:
    order = ["LOW", "MEDIUM", "HIGH"]
    counts = {k: 0 for k in order}
    for r in results:
        if r["severity"]:
            counts[r["severity"]] = counts.get(r["severity"], 0) + 1

    fig = go.Figure(go.Bar(
        x=list(counts.keys()),
        y=list(counts.values()),
        marker_color=[SEVERITY_COLORS.get(k, "#6b7280") for k in counts],
        text=list(counts.values()),
        textposition="outside",
    ))
    fig.update_layout(**PLOTLY_LAYOUT, title="Severity Distribution")
    return fig


def _chart_actions(results: list, run_log: list) -> go.Figure:
    # Prefer run_log (has detail) but fall back to results list
    if run_log:
        counts = {}
        for entry in run_log:
            k = entry["action"]
            counts[k] = counts.get(k, 0) + 1
    else:
        counts = {}
        for r in results:
            k = r["action"] or "UNKNOWN"
            counts[k] = counts.get(k, 0) + 1

    fig = go.Figure(go.Bar(
        x=list(counts.keys()),
        y=list(counts.values()),
        marker_color=[ACTION_COLORS.get(k, "#6b7280") for k in counts],
        text=list(counts.values()),
        textposition="outside",
    ))
    fig.update_layout(**PLOTLY_LAYOUT, title="Actions Taken")
    return fig


def _chart_faults_by_joint(results: list) -> go.Figure:
    counts = {}
    for r in results:
        if r["validation"] and r["validation"] != "OK":
            counts[r["joint"]] = counts.get(r["joint"], 0) + 1

    if not counts:
        fig = go.Figure()
        fig.add_annotation(text="No faults in this batch",
                           xref="paper", yref="paper", x=0.5, y=0.5,
                           showarrow=False, font=dict(color="#8892a4"))
        fig.update_layout(**PLOTLY_LAYOUT, title="Faults by Joint")
        return fig

    sorted_items = sorted(counts.items(), key=lambda x: x[1])
    fig = go.Figure(go.Bar(
        x=[v for _, v in sorted_items],
        y=[k for k, _ in sorted_items],
        orientation="h",
        marker_color="#f59e0b",
        text=[v for _, v in sorted_items],
        textposition="outside",
    ))
    fig.update_layout(**PLOTLY_LAYOUT, title="Faults by Joint")
    return fig


def _chart_routing(results: list) -> go.Figure:
    auto  = sum(1 for r in results if "auto_close" in r["path"])
    full  = len(results) - auto

    fig = go.Figure(go.Pie(
        labels=["Auto-Close (no LLM)", "Full Path (LLM)"],
        values=[auto, full],
        hole=0.55,
        marker_colors=["#3b82f6", "#8b5cf6"],
        textinfo="label+percent",
        textfont_size=10,
    ))
    fig.update_layout(**PLOTLY_LAYOUT, title="Routing Split")
    return fig


def _chart_safety_split(results: list) -> go.Figure:
    counts = {"Critical": 0, "Non-Critical": 0, "Unknown": 0}
    for r in results:
        if r["safety_critical"] is True:
            counts["Critical"] += 1
        elif r["safety_critical"] is False:
            counts["Non-Critical"] += 1
        else:
            counts["Unknown"] += 1

    fig = go.Figure(go.Pie(
        labels=list(counts.keys()),
        values=list(counts.values()),
        hole=0.55,
        marker_colors=["#ef4444", "#22c55e", "#6b7280"],
        textinfo="label+percent",
        textfont_size=10,
    ))
    fig.update_layout(**PLOTLY_LAYOUT, title="Safety-Critical Split")
    return fig


# ── Drift timeline ────────────────────────────────────────────────────────────

def _render_drift_timeline(df_raw: pd.DataFrame):
    df = df_raw.copy()
    df["timestamp_dt"] = pd.to_datetime(df["timestamp"], utc=True)
    df["deviation_pct"] = ((df["actual_torque_nm"] - df["target_torque_nm"])
                           / df["target_torque_nm"] * 100).round(2)

    joints = sorted(df["joint"].unique().tolist())
    col1, col2 = st.columns([2, 1])
    with col1:
        selected_joints = st.multiselect(
            "Filter by joint", joints,
            default=joints[:3],
            help="Select one or more joints to view their torque readings over time.",
        )
    with col2:
        color_by = st.selectbox("Colour by", ["result", "tool_id", "vehicle_model"])

    if not selected_joints:
        st.info("Select at least one joint to display the timeline.")
        return

    filtered = df[df["joint"].isin(selected_joints)]

    color_map = STATUS_COLORS if color_by == "result" else None

    fig = px.scatter(
        filtered,
        x="timestamp_dt",
        y="actual_torque_nm",
        color=color_by,
        color_discrete_map=color_map,
        hover_data=["event_id", "joint", "tool_id", "target_torque_nm",
                    "tolerance_nm", "deviation_pct"],
        labels={
            "timestamp_dt":     "Timestamp",
            "actual_torque_nm": "Actual Torque (Nm)",
        },
    )

    # Add target ± tolerance band per joint
    for joint in selected_joints:
        j_df = filtered[filtered["joint"] == joint]
        if j_df.empty:
            continue
        target  = j_df["target_torque_nm"].iloc[0]
        tol     = j_df["tolerance_nm"].iloc[0]
        t_min   = j_df["timestamp_dt"].min()
        t_max   = j_df["timestamp_dt"].max()

        for y_val, dash in [(target + tol, "dash"), (target - tol, "dash"), (target, "dot")]:
            fig.add_shape(
                type="line",
                x0=t_min, x1=t_max,
                y0=y_val, y1=y_val,
                line=dict(color="#f59e0b", width=1, dash=dash),
                opacity=0.4,
            )

    fig.update_layout(**PLOTLY_LAYOUT, title="Torque Readings Over Time (with target bands)")
    st.plotly_chart(fig, use_container_width=True)


# ── Results table ─────────────────────────────────────────────────────────────

def _render_results_table(results: list):
    rows = []
    for r in results:
        rows.append({
            "Event ID":   r["event_id"],
            "Joint":      r["joint"],
            "Validation": r["validation"] or "ERROR",
            "Severity":   r["severity"] or "",
            "Safety Crit":str(r["safety_critical"]),
            "Path":       " -> ".join(r["path"]),
            "Action":     r["action"] or "",
            "Error":      r["error"] or "",
        })
    df_display = pd.DataFrame(rows)

    # Filter controls
    col1, col2 = st.columns(2)
    with col1:
        val_filter = st.multiselect(
            "Filter by Validation",
            options=df_display["Validation"].unique().tolist(),
            default=[],
        )
    with col2:
        action_filter = st.multiselect(
            "Filter by Action",
            options=df_display["Action"].unique().tolist(),
            default=[],
        )

    if val_filter:
        df_display = df_display[df_display["Validation"].isin(val_filter)]
    if action_filter:
        df_display = df_display[df_display["Action"].isin(action_filter)]

    st.dataframe(df_display, use_container_width=True, hide_index=True)
    st.caption(f"{len(df_display)} rows shown.")
