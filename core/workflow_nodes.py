import logging
from core.validator import validate_torque
from core.decision_agent import run_decision_agent
from core.tools import create_escalation_ticket, log_rework, close_incident

logger = logging.getLogger("torque.nodes")


def validation_node(state):
    result, severity = validate_torque(state)
    state.validation = result
    state.severity = severity
    logger.debug("")
    logger.debug("[VALIDATE]  %s  →  %s  |  severity: %s", state.event_id, result, severity)
    return state


def auto_close_node(state):
    """
    Fast-path for OK events on non-safety-critical joints (LOW severity).
    Calls close_incident() directly — same function the finalize node uses —
    so any future changes to close_incident() cover both paths.
    No RAG calls, no LLM call.
    """
    logger.debug("[AUTO-CLOSE]  %s  |  %s  |  OK + LOW → closed without LLM", state.event_id, state.joint)
    result = close_incident(state.event_id)
    state.agent_result = result
    return state


def create_rag_node(sop_store):
    def rag_node(state):
        from core.rag import retrieve_context
        context = retrieve_context(
            sop_store,
            joint=state.joint,
            vehicle_model=state.vehicle_model,
            validation=state.validation or "",
        )
        state.rag_context = context
        logger.debug("[RAG-SOP]     %s  →  retrieved %d SOP chunks", state.event_id, len(context))
        return state

    return rag_node


def create_incident_rag_node(incident_store):
    def incident_rag_node(state):
        from core.rag import retrieve_incident_context
        context = retrieve_incident_context(
            incident_store,
            joint=state.joint,
            tool_id=state.tool_id,
            validation=state.validation or "",
        )
        state.incident_context = context
        logger.debug("[RAG-INC]     %s  →  retrieved %d incident chunks", state.event_id, len(context))
        return state

    return incident_rag_node


def agent_node(state):
    """
    v2 agent node: calls the reasoning-based decision agent which returns
    a structured AgentDecision. No tool calls happen here — that's the
    finalize node's job.

    The agent's severity assessment overrides the validator's preliminary
    severity (which was only used for routing to the auto-close path).
    """
    decision = run_decision_agent(state)

    state.agent_decision = decision
    state.agent_reasoning = decision.reasoning

    # Agent's severity overrides the validator's preliminary severity
    if decision.severity:
        state.severity = decision.severity

    return state


def finalize_node(state):
    """
    Executes the tool call based on the agent's decision.

    Separating decision from execution enables:
    - Human-in-the-loop checkpoint before execution (Phase 5)
    - Audit logging of both the decision and the execution
    - The agent's structured reasoning to be stored before any side effects

    Maps agent actions to tool functions:
        ESCALATE -> create_escalation_ticket()
        REWORK   -> log_rework()
        CLOSE    -> close_incident()
    """
    decision = state.agent_decision

    if decision is None:
        logger.warning("[FINALIZE] %s — no agent decision available, defaulting to ESCALATE", state.event_id)
        result = create_escalation_ticket(state.event_id, "No agent decision — fail-safe escalation.")
        state.agent_result = result
        return state

    action = decision.action.upper()

    if action == "ESCALATE":
        reason = decision.reasoning or "Escalated by decision agent."
        result = create_escalation_ticket(state.event_id, reason)

    elif action == "REWORK":
        note = decision.recommended_corrective or decision.reasoning or "Rework logged by decision agent."
        result = log_rework(state.event_id, note)

    elif action == "CLOSE":
        result = close_incident(state.event_id)

    else:
        logger.warning("[FINALIZE] %s — unknown action '%s', defaulting to ESCALATE", state.event_id, action)
        result = create_escalation_ticket(state.event_id, f"Unknown agent action: {action}")

    state.agent_result = result
    logger.debug("")
    logger.debug("[FINALIZE]    %s  →  %s", state.event_id, result.get("status", "???"))
    logger.debug("")
    return state