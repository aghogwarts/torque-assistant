"""
app.py — Torque Incident Management UI

Run with:  streamlit run app.py

Four pages:
  Batch Runner      — select events, run the workflow, watch live progress
  Analytics         — charts and statistics from the current or a past run
  Event Inspector   — drill into any single event step by step
  Run History       — browse and download past run reports
"""

import sys
import os

# Ensure project root is on the path so core/ and main.py are importable
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()  # Must be before any imports that need the API key

import streamlit as st

# Page config — must be the first Streamlit call
st.set_page_config(
    page_title="Torque Assistant",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Cached resource loading ───────────────────────────────────────────────────
# @st.cache_resource means these are built once per process and reused across
# all pages, reruns, and users. Without this, the FAISS index and LangGraph
# workflow would be rebuilt on every Streamlit interaction.

@st.cache_resource(show_spinner="Building resources...")
def load_resources():
    from core.loader import load_events
    from core.rag import build_vector_store, build_incident_vector_store
    from core.workflow import build_workflow
    from main import build_spec_lookup

    df                   = load_events("data/torque_events.csv")
    vectorstore          = build_vector_store("data/sop_chunks.json")
    incident_vectorstore = build_incident_vector_store("data/past_incidents.json")
    spec_lookup          = build_spec_lookup("data/sops.json")
    workflow             = build_workflow(vectorstore, incident_vectorstore)

    return {
        "df":                   df,
        "vectorstore":          vectorstore,
        "incident_vectorstore": incident_vectorstore,
        "spec_lookup":          spec_lookup,
        "workflow":             workflow,
    }


# ── Navigation ────────────────────────────────────────────────────────────────

def main():

    # Sidebar
    with st.sidebar:
        st.markdown("### ⚙️ Torque Assistant")
        st.caption("Automobile Assembly Line\nIncident Management System")
        st.divider()

        page = st.radio(
            "Navigate",
            ["Batch Runner", "Analytics", "Event Inspector", "Run History"],
            label_visibility="collapsed",
        )

        st.divider()

        # Quick session state summary
        if st.session_state.get("results"):
            n = len(st.session_state["results"])
            label = st.session_state.get("last_batch_label", "")
            st.caption(f"Last run: **{n} events**")
            if label:
                st.caption(f"`{label}`")
        else:
            st.caption("No run data in session yet.")

    # Load shared resources (cached)
    resources = load_resources()

    # Route to page
    if page == "Batch Runner":
        from ui.batch_runner import render
        render(resources)

    elif page == "Analytics":
        from ui.analytics import render
        render(resources)

    elif page == "Event Inspector":
        from ui.event_inspector import render
        render(resources)

    elif page == "Run History":
        from ui.run_history import render
        render(resources)


if __name__ == "__main__":
    main()
