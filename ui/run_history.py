"""
run_history.py — Page 4: Run History

Lists all past batch runs from run_reports/, lets the user select one,
view the TXT summary, browse the results table, and download all three files.
"""

import json
import os

import pandas as pd
import streamlit as st

from ui.styles import inject_css


def _safe_read(path: str) -> str:
    """
    Read a text file trying utf-8 first, falling back to cp1252.
    Needed because report files written before the encoding fix may be cp1252
    (Windows default) while newer ones are utf-8.
    """
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    # Last resort — replace undecodable bytes
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def render(resources: dict):
    inject_css()

    st.markdown('<div class="section-header">Run History</div>', unsafe_allow_html=True)

    reports_dir = "run_reports"
    if not os.path.exists(reports_dir):
        st.markdown(
            '<div class="info-card">No reports found. Run a batch first to generate reports.</div>',
            unsafe_allow_html=True,
        )
        return

    runs = sorted(
        [d for d in os.listdir(reports_dir)
         if os.path.isdir(os.path.join(reports_dir, d))],
        reverse=True,
    )

    if not runs:
        st.markdown(
            '<div class="info-card">No reports found yet. '
            'Complete a batch run to generate reports.</div>',
            unsafe_allow_html=True,
        )
        return

    selected_run = st.selectbox("Select Run", runs)
    run_dir = os.path.join(reports_dir, selected_run)

    st.divider()

    # ── Download buttons ──────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Download Report Files</div>',
                unsafe_allow_html=True)

    dcol1, dcol2, dcol3 = st.columns(3)

    json_path = os.path.join(run_dir, "report.json")
    csv_path  = os.path.join(run_dir, "report.csv")
    txt_path  = os.path.join(run_dir, "report.txt")

    with dcol1:
        if os.path.exists(json_path):
            st.download_button(
                    "Download JSON",
                    _safe_read(json_path),
                    file_name=f"{selected_run}_report.json",
                    mime="application/json",
                    width='stretch',
                )

    with dcol2:
        if os.path.exists(csv_path):
            st.download_button(
                    "Download CSV",
                    _safe_read(csv_path),
                    file_name=f"{selected_run}_report.csv",
                    mime="text/csv",
                    width='stretch',
                )

    with dcol3:
        if os.path.exists(txt_path):
            st.download_button(
                    "Download TXT",
                    _safe_read(txt_path),
                    file_name=f"{selected_run}_report.txt",
                    mime="text/plain",
                    width='stretch',
                )

    st.divider()

    # ── TXT summary ───────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Run Summary</div>', unsafe_allow_html=True)
    if os.path.exists(txt_path):
        txt_content = _safe_read(txt_path)
        st.code(txt_content, language=None)
    else:
        st.warning("report.txt not found for this run.")

    st.divider()

    # ── Results table from CSV ────────────────────────────────────────────────
    st.markdown('<div class="section-header">Results Table</div>', unsafe_allow_html=True)
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        st.dataframe(df, width='stretch', hide_index=True)
        st.caption(f"{len(df)} events in this run.")
    else:
        st.warning("report.csv not found for this run.")

    st.divider()

    # ── JSON stats ────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Statistics (from JSON)</div>',
                unsafe_allow_html=True)
    if os.path.exists(json_path):
        data = json.loads(_safe_read(json_path))
        summary = data.get("summary", {})

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Validation Counts**")
            vc = summary.get("validation_counts", {})
            for k, v in vc.items():
                st.markdown(f"- `{k}`: **{v}**")

            st.markdown("**Actions**")
            ac = summary.get("actions", {})
            for k, v in ac.items():
                st.markdown(f"- `{k}`: **{v}**")

        with col2:
            st.markdown("**Severity Counts**")
            sc = summary.get("severity_counts", {})
            for k, v in sc.items():
                st.markdown(f"- `{k}`: **{v}**")

            if summary.get("unknown_joints"):
                st.markdown("**Unknown Joints** ⚠")
                for j in summary["unknown_joints"]:
                    st.markdown(f"- `{j}`")

        if summary.get("error_list"):
            st.markdown("**Errors**")
            for e in summary["error_list"]:
                st.markdown(
                    f'<div class="error-card">'
                    f'{e["event_id"]} — {e["error"]}</div>',
                    unsafe_allow_html=True,
                )
