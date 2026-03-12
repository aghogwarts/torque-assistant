from pydantic import BaseModel
from typing import Optional


class TorqueEvent(BaseModel):
    event_id: str
    joint: str
    target_torque_nm: float
    tolerance_nm: float
    actual_torque_nm: float
    angle_required: Optional[float]
    actual_angle_deg: Optional[float]
    # safety_critical intentionally absent — it is a joint engineering spec
    # from sops.json, not a property logged per tightening event.
    # It is resolved in main.py and set directly on IncidentState.
