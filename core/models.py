from pydantic import BaseModel, Field
from typing import List, Optional


class TorqueEvent(BaseModel):
    event_id: str
    joint: str
    vehicle_model: str = ""
    station: str = ""
    tool_id: str = ""
    target_torque_nm: float
    tolerance_nm: float
    actual_torque_nm: float
    angle_required: Optional[float]
    actual_angle_deg: Optional[float]
    # safety_critical intentionally absent — it is a joint engineering spec
    # from sops.json, not a property logged per tightening event.
    # It is resolved in main.py and set directly on IncidentState.


class AgentDecision(BaseModel):
    """
    Structured output from the decision agent.

    Every field is populated by the LLM's reasoning — no pre-computed
    rules. The action field drives the downstream tool call (escalate,
    rework, or close). The remaining fields provide an auditable trace
    of why the decision was made.
    """
    reasoning: str = ""
    severity: str = ""                          # LOW | MEDIUM | HIGH
    action: str = ""                            # ESCALATE | REWORK | CLOSE
    confidence: float = 0.0                     # 0.0 – 1.0
    root_cause_hypothesis: str = ""
    recommended_corrective: str = ""
    sop_references: List[str] = Field(default_factory=list)
