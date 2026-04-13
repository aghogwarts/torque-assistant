"""
decision_agent.py — v2: Reasoning-based decision agent

The agent receives raw event data, SOP context, past incidents, and trend
context, then derives the correct action by reasoning — not by following
pre-coded rules. Output is a structured AgentDecision (JSON-parsed).

The tool functions (escalate, rework, close) are NOT called here. They are
executed downstream in the finalize node based on the agent's decision.
"""

import json
import os
import logging
from dotenv import load_dotenv
from pydantic import SecretStr

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from core.models import AgentDecision

load_dotenv()

logger = logging.getLogger("torque.agent")

api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    raise ValueError("OPENROUTER_API_KEY not set")

# ── Config ────────────────────────────────────────────────────────────────────

# Model can be swapped via env var. Defaults to the free Nemotron model.
# For production quality, set TORQUE_LLM_MODEL=anthropic/claude-sonnet-4.6
MODEL = os.getenv("TORQUE_LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

# Confidence threshold below which decisions are flagged for human review.
# Groundwork for Phase 5 (human-in-the-loop).
CONFIDENCE_THRESHOLD = float(os.getenv("TORQUE_CONFIDENCE_THRESHOLD", "0.90"))


# ── LLM setup ─────────────────────────────────────────────────────────────────

llm = ChatOpenAI(
    model=MODEL,
    base_url="https://openrouter.ai/api/v1",
    api_key=SecretStr(api_key),
    temperature=0,
    max_tokens=1500,
)


# ── Prompt ────────────────────────────────────────────────────────────────────

prompt = ChatPromptTemplate.from_template(
    """You are a senior manufacturing quality engineer reviewing a torque tightening event from an automobile assembly line.

You must analyze the event, determine if it meets specification, assess the severity of any deviation, and decide the correct operational response — based on the SOP instructions and any available context.

Do not assume or rely on any external decision rules. Derive your action entirely from the SOP content, the event data, and your engineering judgment.

═══════════════════════════════════════════
EVENT DATA
═══════════════════════════════════════════
Event ID:            {event_id}
Joint:               {joint}
Vehicle Model:       {vehicle_model}
Station:             {station}
Tool Used:           {tool_id}
Safety-Critical:     {safety_critical}

Target Torque:       {target_torque_nm} Nm
Tolerance:           ±{tolerance_nm} Nm
Actual Torque:       {actual_torque_nm} Nm
Deviation:           {deviation} Nm ({deviation_pct}%)

Angle Required:      {angle_required}
Actual Angle:        {actual_angle_deg}

═══════════════════════════════════════════
SOP INSTRUCTIONS FOR THIS JOINT
═══════════════════════════════════════════
{sop_context}

═══════════════════════════════════════════
SIMILAR PAST INCIDENTS
═══════════════════════════════════════════
{incident_context}

═══════════════════════════════════════════
TREND CONTEXT
═══════════════════════════════════════════
{trend_context}

═══════════════════════════════════════════
YOUR ANALYSIS
═══════════════════════════════════════════

Analyze this event by considering:

1. Does the actual torque fall within the specified tolerance range?
2. If an angle step is specified in the SOP, was the angle measurement recorded?
3. The joint is classified as Safety-Critical: {safety_critical}. Factor this into your severity assessment — a deviation on a safety-critical joint has different implications than on a non-safety joint.
4. How large is the deviation relative to the tolerance window? A marginal deviation (barely outside tolerance) may warrant different handling than a severe one (>2x tolerance).
5. Are there similar past incidents? What root causes and corrective actions were identified?
6. Is there a pattern or trend (multiple recent deviations on the same tool, station, or joint)? A cluster suggests a systemic issue rather than a one-off occurrence.

Based on your analysis, select exactly ONE action:

- ESCALATE — for deviations that pose a safety risk, indicate systemic failure, or affect safety-critical joints in a way that could compromise vehicle integrity. Escalation creates a hold on the affected vehicle and triggers engineering review.

- REWORK — for deviations that need correction but do not pose an immediate safety risk. The vehicle is flagged for re-torque at the rework station.

- CLOSE — for events that meet all specification requirements. No action required.

You MUST respond with ONLY a JSON object. No markdown, no backticks, no explanation outside the JSON.

{{"reasoning": "Your step-by-step analysis (2-4 sentences)", "severity": "LOW or MEDIUM or HIGH", "action": "ESCALATE or REWORK or CLOSE", "confidence": 0.0, "root_cause_hypothesis": "What likely caused this deviation (or N/A if event is within spec)", "recommended_corrective": "Specific next step (or N/A if event is within spec)", "sop_references": ["Which SOP details informed your decision"]}}"""
)


# ── Response parser ───────────────────────────────────────────────────────────

def _parse_decision(raw: str) -> AgentDecision:
    """
    Parse the LLM's raw text response into an AgentDecision.

    Handles common LLM quirks:
    - Markdown backtick wrapping
    - Preamble text before the JSON
    - Truncated responses (returns partial data with low confidence)
    """
    cleaned = raw.strip()

    # Strip markdown backticks
    if "```" in cleaned:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start != -1 and end > start:
            cleaned = cleaned[start:end]
    elif not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start != -1 and end > start:
            cleaned = cleaned[start:end]

    try:
        data = json.loads(cleaned)
        return AgentDecision(**data)
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("[AGENT] Failed to parse decision JSON: %s", exc)
        logger.debug("[AGENT] Raw response:\n%s", raw[:500])
        # Return a conservative fallback — flag for human review
        return AgentDecision(
            reasoning=f"PARSE_ERROR: Could not parse LLM response. Raw: {raw[:200]}",
            severity="HIGH",
            action="ESCALATE",
            confidence=0.0,
            root_cause_hypothesis="Unable to determine — LLM response could not be parsed.",
            recommended_corrective="Manual review required.",
            sop_references=[],
        )


# ── Agent runner ──────────────────────────────────────────────────────────────

def run_decision_agent(state) -> AgentDecision:
    """
    Runs the v2 decision agent. Receives the full IncidentState, formats
    the prompt with all available context, and returns a structured
    AgentDecision.

    The agent does NOT call tools — it returns a decision that the
    finalize node (workflow_nodes.py) will act on.
    """
    # Compute deviation for the prompt
    deviation_nm = state.actual_torque_nm - state.target_torque_nm
    deviation_pct = (deviation_nm / state.target_torque_nm * 100) if state.target_torque_nm else 0

    # Format angle fields for readability
    angle_req_str = f"{state.angle_required} degrees" if state.angle_required is not None else "None (TorqueOnly method)"
    angle_act_str = (
        f"{state.actual_angle_deg} degrees" if state.actual_angle_deg is not None
        else ("NOT RECORDED" if state.angle_required is not None else "N/A")
    )

    # Safety-critical display
    if state.safety_critical is True:
        sc_str = "Yes"
    elif state.safety_critical is False:
        sc_str = "No"
    else:
        sc_str = "Unknown (not found in SOP data — treat as safety-critical)"

    # Trend context — placeholder until Phase 3 trend detection node
    trend_str = state.trend_context or "No active trends detected for this tool or station."

    logger.debug("\n--- AGENT v2 ---")
    logger.debug("Event: %s | Joint: %s | Validation: %s", state.event_id, state.joint, state.validation)
    logger.debug("Safety-Critical: %s | Deviation: %+.1f Nm (%+.1f%%)", sc_str, deviation_nm, deviation_pct)
    logger.debug("RAG context: %d SOP chunks, %d incident chunks", len(state.rag_context), len(state.incident_context))

    formatted = prompt.format(
        event_id=state.event_id,
        joint=state.joint,
        vehicle_model=state.vehicle_model,
        station=state.station,
        tool_id=state.tool_id,
        safety_critical=sc_str,
        target_torque_nm=state.target_torque_nm,
        tolerance_nm=state.tolerance_nm,
        actual_torque_nm=state.actual_torque_nm,
        deviation=f"{deviation_nm:+.1f}",
        deviation_pct=f"{deviation_pct:+.1f}",
        angle_required=angle_req_str,
        actual_angle_deg=angle_act_str,
        sop_context="\n".join(state.rag_context) if state.rag_context else "No SOP context retrieved.",
        incident_context="\n".join(state.incident_context) if state.incident_context else "No similar past incidents found.",
        trend_context=trend_str,
    )

    logger.debug("\n[AGENT] Sending prompt to model (%s)...", MODEL)

    response = llm.invoke(formatted)
    raw = response.content or ""

    logger.debug("[AGENT] Raw response length: %d chars", len(raw))
    # logger.debug("[AGENT] Raw response:\n%s", raw[:500])

    decision = _parse_decision(raw)

    # Log the parsed decision
    logger.debug("[AGENT] Parsed decision: action=%s severity=%s confidence=%.2f",
                 decision.action, decision.severity, decision.confidence)

    if decision.confidence < CONFIDENCE_THRESHOLD:
        logger.info("[AGENT] ⚠ Low confidence (%.2f < %.2f) on %s — flagged for review",
                     decision.confidence, CONFIDENCE_THRESHOLD, state.event_id)

    return decision
