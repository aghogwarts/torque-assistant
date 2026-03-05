def validate_torque(state):

    lower = state.target_torque_nm - state.tolerance_nm
    upper = state.target_torque_nm + state.tolerance_nm

    print(f"[DEBUG] Lower: {lower}, Upper: {upper}, Actual: {state.actual_torque_nm}")

    if state.actual_torque_nm < lower:
        return "UNDER_TORQUE"

    if state.actual_torque_nm > upper:
        return "OVER_TORQUE"

    if state.angle_required is not None:
        if state.actual_angle_deg is None:
            return "ANGLE_MISSING"

    return "OK"
