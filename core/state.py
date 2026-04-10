from typing import List, Optional
from pydantic import BaseModel
from core.models import AgentDecision


class IncidentState(BaseModel):
    event_id: str
    joint: str

    # New fields for the v2 agent prompt — needed so the LLM sees the full
    # context of the event without relying on pre-digested labels.
    vehicle_model: str = ""
    station: str = ""
    tool_id: str = ""

    target_torque_nm: float
    actual_torque_nm: float
    tolerance_nm: float

    angle_required: Optional[float] = None
    actual_angle_deg: Optional[float] = None

    # Resolved from sops.json spec lookup in main.py before the graph runs.
    # None means the joint was not found in SOP data — treated as HIGH (fail-safe).
    safety_critical: Optional[bool] = None

    incident_context: List[str] = []

    validation: Optional[str] = None
    severity: Optional[str] = None  # LOW | MEDIUM | HIGH (set by validator for routing, may be overridden by agent)
    rag_context: List[str] = []

    # Trend context injected by trend detection node (Phase 3).
    # For now, defaults to empty — the agent prompt handles "no trends" gracefully.
    trend_context: str = ""

    # ── Agent output (v2: structured decision) ────────────────────────────
    agent_result: Optional[dict] = None
    agent_decision: Optional[AgentDecision] = None
    # Kept for backward compat with existing UI code; v2 populates this
    # from agent_decision.reasoning.
    agent_reasoning: Optional[str] = None
