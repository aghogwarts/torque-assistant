import json
from dotenv import load_dotenv

load_dotenv()

from core.loader import load_events, event_from_row
from core.rag import build_vector_store, build_incident_vector_store
from core.workflow import build_workflow
from core.state import IncidentState


def build_spec_lookup(sops_path: str) -> dict:
    """
    Builds a {joint_name -> safety_critical} dict from sops.json.

    This is the authoritative source for whether a joint is safety-critical.
    It is a joint engineering spec — not event-level data — so it belongs
    here at startup, not inside any workflow node.

    Used in build_state() to pre-populate state.safety_critical before
    the graph runs, ensuring the validator and any future router both
    see the correct value from the very first node.
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


def main():

    df = load_events("data/torque_events.csv")
    incident_vectorstore = build_incident_vector_store("data/past_incidents.json")
    vectorstore = build_vector_store("data/sop_chunks.json")

    # Build the joint → safety_critical lookup once at startup.
    spec_lookup = build_spec_lookup("data/sops.json")
    print(f"[INIT] Spec lookup built — {len(spec_lookup)} joints resolved from SOPs.")

    workflow = build_workflow(vectorstore, incident_vectorstore)

    event = event_from_row(df.iloc[38])

    # safety_critical resolved here — not from CSV, not inside any node.
    state = build_state(event, spec_lookup)

    print("\n--- WORKFLOW EXECUTION ---")

    for step in workflow.stream(state):
        node = list(step.keys())[0]
        if node == "validate":
            print("\n[VALIDATION COMPLETE]")
        elif node == "rag":
            print("[SOP RETRIEVAL COMPLETE]")
        elif node == "rag_incidents":
            print("[INCIDENT HISTORY RETRIEVAL COMPLETE]")
        elif node == "agent":
            print("[AGENT DECISION COMPLETE]")


if __name__ == "__main__":
    main()
