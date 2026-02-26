from dotenv import load_dotenv

load_dotenv()

from core.loader import load_events, event_from_row
from core.validator import validate_torque
from core.analyzer import analyze_incident
from core.rag import build_vector_store, retrieve_context


def main():
    df = load_events("data/torque_events.csv")

    # build vector store once
    vectorstore = build_vector_store("data/sop_chunks.json")

    sample_row = df.iloc[0]
    event = event_from_row(sample_row)

    validation = validate_torque(event)

    # build retrieval query
    query = f"{event.joint} {validation}"

    context = retrieve_context(vectorstore, query)

    result = analyze_incident(event, validation)

    print("\n=== INCIDENT ANALYSIS ===")
    print(result)

    print("\n=== RETRIEVED SOP CONTEXT ===")
    for c in context:
        print("-", c)


if __name__ == "__main__":
    main()
