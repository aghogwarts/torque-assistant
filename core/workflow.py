from langgraph.graph import StateGraph, END
from core.state import IncidentState
from core.workflow_nodes import (
    validation_node,
    auto_close_node,
    create_rag_node,
    create_incident_rag_node,
    agent_node,
)


def route_after_validate(state: IncidentState) -> str:
    """
    Decides the path immediately after validation.

    auto_close → OK result AND non-safety-critical joint (LOW severity)
                 No RAG, no LLM. close_incident() called directly.

    rag        → everything else:
                 - any deviation (UNDER_TORQUE, OVER_TORQUE, ANGLE_MISSING)
                 - OK result on a safety-critical joint (HIGH severity)
                 - OK result on an unknown joint (None → HIGH, fail-safe)

    severity is already correctly set by validate_torque() because
    safety_critical was pre-populated on state in main.py before the
    graph started — so this check is safe to make here.
    """
    if state.validation == "OK" and state.severity == "LOW":
        return "auto_close"
    return "rag"


def build_workflow(vectorstore, incident_vectorstore):

    graph = StateGraph(IncidentState)

    rag_node = create_rag_node(vectorstore)
    incident_rag_node = create_incident_rag_node(incident_vectorstore)

    graph.add_node("validate", validation_node)
    graph.add_node("auto_close", auto_close_node)
    graph.add_node("rag", rag_node)
    graph.add_node("rag_incidents", incident_rag_node)
    graph.add_node("agent", agent_node)

    graph.set_entry_point("validate")

    # Single conditional branch — replaces the old linear edge from validate→rag
    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "auto_close": "auto_close",
            "rag": "rag",
        },
    )

    graph.add_edge("auto_close", END)
    graph.add_edge("rag", "rag_incidents")
    graph.add_edge("rag_incidents", "agent")
    graph.add_edge("agent", END)

    return graph.compile()
