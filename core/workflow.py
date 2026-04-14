from langgraph.graph import StateGraph, END
from core.state import IncidentState
from core.workflow_nodes import (
    validation_node,
    auto_close_node,
    create_trend_node,
    create_rag_node,
    create_incident_rag_node,
    agent_node,
    finalize_node,
)


def route_after_validate(state: IncidentState) -> str:
    """
    Decides the path immediately after validation.

    auto_close → OK result AND non-safety-critical joint (LOW severity)
                 No RAG, no LLM. close_incident() called directly.

    trend      → everything else goes through trend detection first,
                 then RAG, then the agent.
    """
    if state.validation == "OK" and state.severity == "LOW":
        return "auto_close"
    return "trend"


def build_workflow(vectorstore, incident_vectorstore, trend_detector=None):

    graph = StateGraph(IncidentState)

    trend_node = create_trend_node(trend_detector) if trend_detector else None
    rag_node = create_rag_node(vectorstore)
    incident_rag_node = create_incident_rag_node(incident_vectorstore)

    graph.add_node("validate", validation_node)
    graph.add_node("auto_close", auto_close_node)
    if trend_node:
        graph.add_node("trend", trend_node)
    graph.add_node("rag", rag_node)
    graph.add_node("rag_incidents", incident_rag_node)
    graph.add_node("agent", agent_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("validate")

    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "auto_close": "auto_close",
            "trend": "trend" if trend_node else "rag",
        },
    )

    graph.add_edge("auto_close", END)

    if trend_node:
        graph.add_edge("trend", "rag")

    graph.add_edge("rag", "rag_incidents")
    graph.add_edge("rag_incidents", "agent")
    graph.add_edge("agent", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()