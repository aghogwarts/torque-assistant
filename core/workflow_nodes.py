from core.validator import validate_torque
from core.rag import retrieve_context
from core.decision_agent import run_decision_agent

vectorstore = None


def validation_node(state):
    result = validate_torque(state)
    state.validation = result
    return state


def rag_node(state):
    query = f"{state.joint} {state.validation}"
    context = retrieve_context(vectorstore, query)
    state.rag_context = context
    return state


def agent_node(state):
    result = run_decision_agent(state, state.validation, state.rag_context)
    state.agent_result = result
    return state
