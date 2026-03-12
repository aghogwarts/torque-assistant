from core.validator import validate_torque
from core.rag import retrieve_context, retrieve_incident_context
from core.decision_agent import run_decision_agent
from core.tools import close_incident


def validation_node(state):
    result, severity = validate_torque(state)
    state.validation = result
    state.severity = severity
    return state


def auto_close_node(state):
    """
    Fast-path for OK events on non-safety-critical joints (LOW severity).
    Calls close_incident() directly — same function the agent uses via
    close_tool — so the logging refactor in a later step covers both paths.
    No RAG calls, no LLM call.
    """
    print(f"[AUTO-CLOSE] {state.event_id} | {state.joint} | OK + LOW severity")
    result = close_incident(state.event_id)
    state.agent_result = result
    return state


def create_rag_node(vectorstore):
    def rag_node(state):
        query = f"{state.joint} {state.validation}"
        context = retrieve_context(vectorstore, query)
        state.rag_context = context
        return state

    return rag_node


def create_incident_rag_node(vectorstore):
    def incident_rag_node(state):
        query = f"{state.joint} {state.validation}"
        context = retrieve_incident_context(vectorstore, query)
        state.incident_context = context
        return state

    return incident_rag_node


def agent_node(state):
    result = run_decision_agent(
        state, state.validation, state.rag_context, state.incident_context
    )
    state.agent_result = result
    return state
