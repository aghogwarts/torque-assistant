import pandas as pd
from core.models import TorqueEvent


def load_events(path: str):
    df = pd.read_csv(path)
    return df


def event_from_row(row) -> TorqueEvent:
    return TorqueEvent(
        event_id=row["event_id"],
        joint=row["joint"],
        target_torque_nm=row["target_torque_nm"],
        tolerance_nm=row["tolerance_nm"],
        actual_torque_nm=row["actual_torque_nm"],
        angle_required=row.get("angle_required"),
        actual_angle_deg=row.get("actual_angle_deg"),
        safety_critical=row.get("safety_critical", False),
    )
