from dotenv import load_dotenv

load_dotenv()

from core.loader import load_events, event_from_row
from core.validator import validate_torque
from core.rag import build_vector_store, retrieve_context
from core.llm_reasoner import reason_with_llm


def main():
    df = load_events("data/torque_events.csv")

    vectorstore = build_vector_store("data/sop_chunks.json")

    sample_row = df.iloc[0]
    event = event_from_row(sample_row)

    validation = validate_torque(event)

    query = f"{event.joint} {validation}"
    context = retrieve_context(vectorstore, query)

    llm_output = reason_with_llm(event, validation, context)

    print("\n=== LLM DECISION ===")
    print(llm_output)


if __name__ == "__main__":
    main()
