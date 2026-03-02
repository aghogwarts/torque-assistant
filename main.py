from dotenv import load_dotenv

load_dotenv()

from core.loader import load_events, event_from_row
from core.validator import validate_torque
from core.rag import build_vector_store, retrieve_context
from core.llm_reasoner import reason_with_llm

from core.decision_agent import run_decision_agent

VERBOSE = True


def main():
    if VERBOSE:
        print("\n[START] Torque Assistant Initialized\n")

    df = load_events("data/torque_events.csv")

    if VERBOSE:
        print(f"[LOAD] Loaded {len(df)} events")

    vectorstore = build_vector_store("data/sop_chunks.json")

    if VERBOSE:
        print("[RAG] Vector store built successfully")

    sample_row = df.iloc[0]
    event = event_from_row(sample_row)

    if VERBOSE:
        print("\n[EVENT]")
        print(event)

    validation = validate_torque(event)

    if VERBOSE:
        print(f"\n[VALIDATE] Result: {validation}")

    query = f"{event.joint} {validation}"

    if VERBOSE:
        print(f"\n[RAG] Query: {query}")

    context = retrieve_context(vectorstore, query)

    if VERBOSE:
        print(f"[RAG] Retrieved {len(context)} chunks:")
        for c in context:
            print("  -", c)

    llm_output = reason_with_llm(event, validation, context)

    print("\n=== [LLM DECISION] ===")
    print(llm_output)

    agent_result = run_decision_agent(event, validation, context)

    print("\n[=== AGENT RESULT ===]")
    print(agent_result)

    print("\n[END]\n")


if __name__ == "__main__":
    main()
