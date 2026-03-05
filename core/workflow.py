from langgraph.graph import StateGraph, END
from core.state import IncidentState
from core.workflow_nodes import (
    validation_node,
    create_rag_node,
    create_incident_rag_node,
    agent_node,
)


def build_workflow(vectorstore, incident_vectorstore):

    graph = StateGraph(IncidentState)

    rag_node = create_rag_node(vectorstore)
    incident_rag_node = create_incident_rag_node(incident_vectorstore)

    graph.add_node("validate", validation_node)
    graph.add_node("rag", rag_node)
    graph.add_node("rag_incidents", incident_rag_node)
    graph.add_node("agent", agent_node)

    graph.set_entry_point("validate")

    graph.add_edge("validate", "rag")
    graph.add_edge("rag", "rag_incidents")
    graph.add_edge("rag_incidents", "agent")
    graph.add_edge("agent", END)

    return graph.compile()
