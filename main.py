from dotenv import load_dotenv

load_dotenv()

from core.loader import load_events, event_from_row
from core.rag import build_vector_store
from core.workflow import build_workflow
from core.state import IncidentState


def main():

    df = load_events("data/torque_events.csv")
    vectorstore = build_vector_store("data/sop_chunks.json")

    event = event_from_row(df.iloc[0])

    workflow = build_workflow(vectorstore)

    state = IncidentState(
        event_id=event.event_id,
        joint=event.joint,
        target_torque_nm=event.target_torque_nm,
        actual_torque_nm=event.actual_torque_nm,
        tolerance_nm=event.tolerance_nm,
        angle_required=event.angle_required,
        actual_angle_deg=event.actual_angle_deg,
        safety_critical=event.safety_critical,
    )

    print("\n--- WORKFLOW EXECUTION ---")

    for step in workflow.stream(state):
        print(f"\n {step}")


if __name__ == "__main__":
    main()
