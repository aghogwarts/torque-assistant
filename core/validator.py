def validate_torque(state) -> tuple[str, str]:
    """
    Returns (validation_result, severity).

    validation_result: OK | UNDER_TORQUE | OVER_TORQUE | ANGLE_MISSING
    severity:          LOW | MEDIUM | HIGH
    """
    lower = state.target_torque_nm - state.tolerance_nm
    upper = state.target_torque_nm + state.tolerance_nm

    if state.actual_torque_nm < lower:
        result = "UNDER_TORQUE"
    elif state.actual_torque_nm > upper:
        result = "OVER_TORQUE"
    elif state.angle_required is not None and state.actual_angle_deg is None:
        result = "ANGLE_MISSING"
    else:
        result = "OK"

    # Severity — previously lived in the now-removed analyzer.py
    if result == "OK":
        severity = "LOW"
    elif state.safety_critical:
        severity = "HIGH"
    else:
        severity = "MEDIUM"

    return result, severity
