"""
batch_runner.py — Page 1: Batch Runner

Lets the user select events (all / single / date range), run the workflow,
watch live progress, and navigate to the report after the run completes.
"""

import pandas as pd
import streamlit as st

from core.loader import event_from_row
from core.tools import RUN_LOG, clear_run_log
from core.reporter import save_report
from main import run_event, build_state
from ui.styles import inject_css, validation_badge, severity_badge, action_badge


def render(resources: dict):
    inject_css()

    df         = resources["df"]
    workflow   = resources["workflow"]
    spec_lookup = resources["spec_lookup"]

    st.markdown('<div class="section-header">Batch Runner</div>', unsafe_allow_html=True)

    # ── Event selection ───────────────────────────────────────────────────────
    mode = st.radio(
        "Event Selection",
        ["All Events", "Single Event", "Date Range"],
        horizontal=True,
        help="Choose which events to run through the workflow.",
    )

    batch_df = _select_events(df, mode)

    if batch_df is None or len(batch_df) == 0:
        st.warning("No events match the current selection.")
        return

    # Preview
    with st.expander(f"Preview — {len(batch_df)} event(s) selected", expanded=False):
        st.dataframe(
            batch_df[["event_id", "timestamp", "joint", "vehicle_model",
                       "tool_id", "actual_torque_nm", "result"]].head(10),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    # ── Run controls ──────────────────────────────────────────────────────────
    col1, col2 = st.columns([3, 1])
    with col1:
        verbose = st.toggle(
            "Verbose logging",
            value=False,
            help="When on, detailed agent reasoning appears in the terminal. "
                 "Has no effect on what's shown in this UI.",
        )
    with col2:
        run_clicked = st.button(
            "Run Batch",
            type="primary",
            disabled=st.session_state.get("running", False),
            use_container_width=True,
        )

    # ── Execute ───────────────────────────────────────────────────────────────
    if run_clicked:
        _execute_batch(batch_df, workflow, spec_lookup, verbose)

    # ── Post-run summary ──────────────────────────────────────────────────────
    if st.session_state.get("run_complete") and st.session_state.get("results"):
        _show_summary(st.session_state["results"])


# ── Event selection helpers ───────────────────────────────────────────────────

def _select_events(df: pd.DataFrame, mode: str) -> pd.DataFrame | None:

    if mode == "All Events":
        max_e = st.slider(
            "Max Events",
            min_value=1,
            max_value=len(df),
            value=min(20, len(df)),
            help="Cap the number of events to process. Set to the max for the full dataset.",
        )
        return df.head(max_e)

    elif mode == "Single Event":
        search = st.text_input("Search by Event ID", placeholder="EVT-0000...")
        ids = df["event_id"].tolist()
        if search:
            ids = [e for e in ids if search.lower() in e.lower()]
        if not ids:
            st.warning("No events match your search.")
            return None
        selected = st.selectbox("Select Event", ids)
        return df[df["event_id"] == selected]

    elif mode == "Date Range":
        df = df.copy()
        df["timestamp_dt"] = pd.to_datetime(df["timestamp"], utc=True)
        min_date = df["timestamp_dt"].min().date()
        max_date = df["timestamp_dt"].max().date()

        date_range = st.date_input(
            "Select Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        if len(date_range) != 2:
            st.info("Select a start and end date.")
            return None
        start, end = date_range
        mask = (df["timestamp_dt"].dt.date >= start) & (df["timestamp_dt"].dt.date <= end)
        filtered = df[mask].drop(columns=["timestamp_dt"])
        st.caption(f"{len(filtered)} events in selected range.")
        return filtered

    return None


# ── Batch execution ───────────────────────────────────────────────────────────

def _execute_batch(batch_df, workflow, spec_lookup, verbose):
    st.session_state["running"]      = True
    st.session_state["run_complete"] = False
    st.session_state["results"]      = []
    st.session_state["run_log"]      = []

    clear_run_log()

    total = len(batch_df)

    # Live counter row
    c1, c2, c3, c4 = st.columns(4)
    cnt_processed  = c1.empty()
    cnt_autoclosed = c2.empty()
    cnt_llm        = c3.empty()
    cnt_errors     = c4.empty()

    progress_bar   = st.progress(0.0, text="Starting...")
    table_slot     = st.empty()

    results = []

    for i, (_, row) in enumerate(batch_df.iterrows(), start=1):
        event  = event_from_row(row)
        result = run_event(workflow, event, spec_lookup)
        results.append(result)

        # Live counters
        errors      = sum(1 for r in results if r["error"])
        auto_closed = sum(1 for r in results if "auto_close" in r["path"])
        llm_used    = i - auto_closed - errors

        cnt_processed.metric("Processed",  f"{i} / {total}")
        cnt_autoclosed.metric("Auto-Closed", auto_closed)
        cnt_llm.metric("LLM Path", llm_used)
        cnt_errors.metric("Errors", errors)

        progress_bar.progress(i / total, text=f"Processing {result['event_id']}...")

        # Live results table (last 15 rows for readability)
        display_df = _results_to_display_df(results[-15:])
        table_slot.dataframe(display_df, use_container_width=True, hide_index=True)

    progress_bar.progress(1.0, text="Complete.")

    # Persist to session state
    st.session_state["results"]      = results
    st.session_state["run_log"]      = list(RUN_LOG)
    st.session_state["running"]      = False
    st.session_state["run_complete"] = True

    # Save report files
    first_id    = batch_df.iloc[0]["event_id"]
    last_id     = batch_df.iloc[-1]["event_id"]
    batch_label = f"batch_{first_id}_to_{last_id}"
    save_report(results, list(RUN_LOG), batch_label)
    st.session_state["last_batch_label"] = batch_label

    st.rerun()


# ── Post-run summary ──────────────────────────────────────────────────────────

def _show_summary(results: list):
    st.markdown('<div class="section-header">Run Complete</div>', unsafe_allow_html=True)

    total       = len(results)
    errors      = sum(1 for r in results if r["error"])
    auto_closed = sum(1 for r in results if "auto_close" in r["path"])
    llm_used    = total - auto_closed - errors
    escalated   = sum(1 for r in results if r["action"] == "ESCALATED")
    reworks     = sum(1 for r in results if r["action"] == "REWORK_LOGGED")
    faults      = sum(1 for r in results if r["validation"] and r["validation"] != "OK")

    cols = st.columns(6)
    metrics = [
        ("Total",       total,       None),
        ("Auto-Closed", auto_closed, None),
        ("LLM Path",    llm_used,    None),
        ("Faults",      faults,      "inverse" if faults > 0 else "off"),
        ("Escalated",   escalated,   "inverse" if escalated > 0 else "off"),
        ("Errors",      errors,      "inverse" if errors > 0 else "off"),
    ]
    for col, (label, val, delta_color) in zip(cols, metrics):
        col.metric(label, val)

    # Full results table
    st.markdown('<div class="section-header" style="margin-top:1rem;">All Results</div>',
                unsafe_allow_html=True)
    st.dataframe(
        _results_to_display_df(results),
        use_container_width=True,
        hide_index=True,
    )

    label = st.session_state.get("last_batch_label", "")
    if label:
        st.markdown(
            f'<div class="info-card">Report saved to <code>run_reports/{label}/</code> '
            f'— view it in the <b>Run History</b> tab.</div>',
            unsafe_allow_html=True,
        )


# ── Display helpers ───────────────────────────────────────────────────────────

def _results_to_display_df(results: list) -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append({
            "Event ID":       r["event_id"],
            "Joint":          r["joint"],
            "Validation":     r["validation"] or "ERROR",
            "Severity":       r["severity"] or "",
            "Safety Critical":str(r["safety_critical"]),
            "Path":           " -> ".join(r["path"]),
            "Action":         r["action"] or "",
            "Error":          r["error"] or "",
        })
    return pd.DataFrame(rows)
