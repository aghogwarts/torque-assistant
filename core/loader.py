import math
import pandas as pd
from core.models import TorqueEvent


def load_events(path: str):
    df = pd.read_csv(path)
    return df


def _nan_to_none(value):
    """
    Pandas reads empty CSV cells as numpy.float64(nan).
    Pydantic Optional[float] fields expect None, not nan.
    Without this, angle_required = nan passes the 'is not None' check
    in the validator and incorrectly triggers ANGLE_MISSING.
    """
    try:
        if math.isnan(float(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value if value != "" else None


def event_from_row(row) -> TorqueEvent:
    return TorqueEvent(
        event_id=row["event_id"],
        joint=row["joint"],
        vehicle_model=row.get("vehicle_model", ""),
        station=row.get("station", ""),
        tool_id=row.get("tool_id", ""),
        target_torque_nm=float(row["target_torque_nm"]),
        tolerance_nm=float(row["tolerance_nm"]),
        actual_torque_nm=float(row["actual_torque_nm"]),
        angle_required=_nan_to_none(row.get("angle_required")),
        actual_angle_deg=_nan_to_none(row.get("actual_angle_deg")),
        # safety_critical is NOT read from the CSV.
        # It is a joint engineering spec defined in sops.json,
        # resolved in main.py via spec_lookup before the graph runs.
    )
