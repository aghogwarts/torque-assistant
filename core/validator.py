def validate_torque(state) -> tuple[str, str]:
    """
    Returns (validation_result, severity).

    validation_result: OK | UNDER_TORQUE | OVER_TORQUE | ANGLE_MISSING
    severity:          LOW | MEDIUM | HIGH

    severity rules:
      OK result                         → LOW
      deviation + safety_critical=True  → HIGH
      deviation + safety_critical=None  → HIGH  (unknown joint = fail-safe)
      deviation + safety_critical=False → MEDIUM
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

    # None (unknown joint) is treated as True — fail-safe for manufacturing.
    # An unnecessary escalation is recoverable; a missed safety issue is not.
    is_critical = state.safety_critical is True or state.safety_critical is None

    if result == "OK":
        severity = "LOW"
    elif is_critical:
        severity = "HIGH"
    else:
        severity = "MEDIUM"

    return result, severity
