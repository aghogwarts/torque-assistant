import json
from dotenv import load_dotenv

load_dotenv()

from core.loader import load_events, event_from_row
from core.rag import build_vector_store, build_incident_vector_store
from core.workflow import build_workflow
from core.state import IncidentState

# ── Config ────────────────────────────────────────────────────────────────────

# Set to an int (e.g. 20) to cap the run during testing.
# Set to None to process the full dataset.
MAX_EVENTS = 50

# ── Startup helpers ───────────────────────────────────────────────────────────


def build_spec_lookup(sops_path: str) -> dict:
    """
    Builds a {joint_name -> safety_critical} dict from sops.json.

    This is the authoritative source for whether a joint is safety-critical.
    It is a joint engineering spec — not event-level data — so it belongs
    here at startup, not inside any workflow node.

    Used in build_state() to pre-populate state.safety_critical before
    the graph runs, ensuring the validator and router both see the
    correct value from the very first node.
    """
    with open(sops_path) as f:
        sops = json.load(f)

    lookup = {}
    for sop in sops:
        joint = sop["joint"]
        # First SOP entry per joint wins — all entries for the same joint
        # share the same safety_critical value across vehicle models.
        if joint not in lookup:
            lookup[joint] = sop["safety_critical"]
    return lookup


def build_state(event, spec_lookup: dict) -> IncidentState:
    """
    Constructs the initial workflow state for one event.

    safety_critical is resolved here from spec_lookup by joint name.
    If the joint is not found in SOP data, it defaults to None —
    the validator treats None as HIGH (fail-safe / conservative).
    """
    safety_critical = spec_lookup.get(event.joint)  # None if joint unknown

    if safety_critical is None:
        # Surface unknown joints clearly so they can be audited.
        print(
            f"[WARN] Joint '{event.joint}' not found in SOP spec lookup — "
            f"treating as safety-critical (fail-safe)."
        )

    return IncidentState(
        event_id=event.event_id,
        joint=event.joint,
        target_torque_nm=event.target_torque_nm,
        actual_torque_nm=event.actual_torque_nm,
        tolerance_nm=event.tolerance_nm,
        angle_required=event.angle_required,
        actual_angle_deg=event.actual_angle_deg,
        safety_critical=safety_critical,
    )


# ── Per-event runner ──────────────────────────────────────────────────────────


def run_event(workflow, event, spec_lookup: dict) -> dict:
    """
    Runs one event through the workflow and returns a result summary dict.

    Wrapped in try/except so a single API error or unexpected exception
    does not abort the entire batch — the error is recorded in the result
    and the loop continues with the next event.
    """
    state = build_state(event, spec_lookup)
    path_taken = []

    try:
        for step in workflow.stream(state):
            node = list(step.keys())[0]
            state = list(step.values())[0]
            path_taken.append(node)

        # LangGraph stream yields state as a plain dict, not as IncidentState.
        # Use dict.get() for all field access after the stream loop.
        agent_result = state.get("agent_result") or {}
        return {
            "event_id": event.event_id,
            "joint": event.joint,
            "validation": state.get("validation"),
            "severity": state.get("severity"),
            "safety_critical": state.get("safety_critical"),
            "path": path_taken,
            "action": agent_result.get("status"),
            "error": None,
        }

    except Exception as exc:
        # state may be a dict (if stream started) or IncidentState (if it failed
        # before the first step). Handle both.
        sc = (
            state.get("safety_critical")
            if isinstance(state, dict)
            else state.safety_critical
        )
        return {
            "event_id": event.event_id,
            "joint": event.joint,
            "validation": None,
            "severity": None,
            "safety_critical": sc,
            "path": path_taken,
            "action": "ERROR",
            "error": str(exc),
        }


# ── Main ──────────────────────────────────────────────────────────────────────


def main():

    # --- Startup ---
    print("[INIT] Loading events...")
    df = load_events("data/torque_events.csv")

    # Apply cap if MAX_EVENTS is set
    if MAX_EVENTS is not None:
        df = df.head(MAX_EVENTS)
        print(
            f"[INIT] MAX_EVENTS={MAX_EVENTS} — processing {len(df)} of {MAX_EVENTS} events"
        )
    else:
        print(f"[INIT] Processing all {len(df)} events")

    print("[INIT] Building vector stores...")
    vectorstore = build_vector_store("data/sop_chunks.json")
    incident_vectorstore = build_incident_vector_store("data/past_incidents.json")

    print("[INIT] Building spec lookup...")
    spec_lookup = build_spec_lookup("data/sops.json")
    print(f"[INIT] {len(spec_lookup)} joints resolved from SOPs")

    print("[INIT] Compiling workflow...")
    workflow = build_workflow(vectorstore, incident_vectorstore)

    total = len(df)

    # --- Batch loop ---
    print(f"\n[BATCH] Starting — {total} events\n")

    results = []

    for i, (_, row) in enumerate(df.iterrows(), start=1):
        event = event_from_row(row)
        result = run_event(workflow, event, spec_lookup)
        results.append(result)

        # Single compact status line per event so progress is visible
        # without drowning in per-node prints from the workflow itself.
        path_str = " → ".join(result["path"])
        status = (
            f"[{i:>4}/{total}] {result['event_id']}  "
            f"{result['joint']:<30}  "
            f"{result['validation'] or 'ERROR':<15}  "
            f"{result['severity'] or '':<8}  "
            f"{path_str}"
        )

        if result["error"]:
            print(f"{status}  !! {result['error']}")
        else:
            print(status)

    # --- End of run summary (counts only — full report comes in logging step) ---
    errors = sum(1 for r in results if r["error"])
    auto_closed = sum(1 for r in results if "auto_close" in r["path"])
    llm_used = total - auto_closed

    print(f"\n[DONE] {total} events processed")
    print(f"       auto-closed (no LLM) : {auto_closed}")
    print(f"       full path (LLM used) : {llm_used}")
    if errors:
        print(f"       errors               : {errors}")


if __name__ == "__main__":
    main()
