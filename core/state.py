from typing import List, Optional
from pydantic import BaseModel


class IncidentState(BaseModel):
    event_id: str
    joint: str

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
    severity: Optional[str] = None  # LOW | MEDIUM | HIGH
    rag_context: List[str] = []
    agent_result: Optional[dict] = None
