def analyze_incident(event, validation_result):
    severity = "LOW"

    if validation_result in ["UNDER_TORQUE", "OVER_TORQUE"]:
        severity = "MEDIUM"

    if event.safety_critical and validation_result != "OK":
        severity = "HIGH"

    return {
        "event_id": event.event_id,
        "validation": validation_result,
        "severity": severity,
        "escalate": severity == "HIGH",
    }
