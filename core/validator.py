def validate_torque(event):
    lower = event.target_torque_nm - event.tolerance_nm
    upper = event.target_torque_nm + event.tolerance_nm

    print(f"[DEBUG] Lower: {lower}, Upper: {upper}, Actual: {event.actual_torque_nm}")

    if event.actual_torque_nm < lower:
        return "UNDER_TORQUE"

    if event.actual_torque_nm > upper:
        return "OVER_TORQUE"

    if event.angle_required is not None:
        if event.actual_angle_deg is None:
            return "ANGLE_MISSING"

    return "OK"
